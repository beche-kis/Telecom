import json
import re 
import time
import logging
import os 
import boto3
from datetime import datetime,timezone 
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel
from utils import clean_response, run_agent_with_retry,log_routing_decision
from docs import TICKETS , ROUTING_RULES,INTENT_TO_AGENT,PRIORITY_PATTERNS


load_dotenv()
logging.basicConfig(level = logging.WARNING)



AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")


ROUTING_AUDIT_TABLE = os.environ.get("ROUTING_AUDIT_TABLE", "Telecom-routing-audit")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
audit_table = dynamodb.Table(ROUTING_AUDIT_TABLE)


classification_result ={}
worker_response ={}


def priority_route( text:str) ->str | None:
    """Check if ticket contains cancellation intent ."""
    text_lower = text.lower()
    for pattern in PRIORITY_PATTERNS:
        if re.search(pattern, text_lower):
            return "RetentionAgent"
    return None 
    
def rule_based_route(text:str) ->str | None:
    """
    Match request text against keyword rules.
    Returns target agent name or None if no rule matches.
    """
    text_lower = text.lower()
    for pattern, agent_name in ROUTING_RULES:
        if re.search(pattern , text_lower):
            return agent_name
        return None 
    
def _verify_audit_table():
    """Verify the DynamoDB  audit table exists and is accessible"""
    try:
        status = audit_table.table_status
        print(f" ✔️ DynamoDB audit_table :{ROUTING_AUDIT_TABLE} ({status})")
    except Exception as e :
        print (f" ✖️ Cannot access DynamoDB table '{ROUTING_AUDIT_TABLE}':{e}")
        print(f" Deploy infrastructure first: aws cloudformation deploy "
              f"--template-file infrastructure/stack.yaml "
              f"--stack-name lesson-stack --capabilities CAPABILITY_NAMED_IAM")
        raise SystemExit(1)


def build_classifier_agent() ->Agent :
    """LLM-powered intent classifier for ambiguous telecom tickets ."""

    @tool
    def classify_intent(intent:str, confidence:float) -> str:
        """
        Record the classified intent and confidence score .

        Args:
            intent: One of billing,technical, cancellation, general
            confidence : Confidence score from 0.0 to 1.0
        Returns :
            JSON confirmation of classification
        """ 
        classification_result["intent"] = intent.lower().strip()
        classification_result["confidence"] = min(max(float(confidence),0.0),1.0)
        return json.dumps(classification_result, indent = 2)

    
    model = BedrockModel(
        model_id = NOVA_LITE_MODEL,
        region_name = AWS_REGION,
        temperature =0.0
    )
    system_prompt  ="""
        You are an intent classifier agent  for telecom service provider.

        Classify the customer request nto One of these intents:
        - billing : bill, rates, subscription ,invoices 
        - technical : signal ,dropped ,disconnect no services , Tower info
        -cancellation : cancel,terminate, switch provider 
        -general : unclear, off-topic or doesnt fit other categories 
       
        Call classify-intent with:
        - intent : one of [billing, technical,cancellation, general]
        -confidence : your confidence from 0.0 to 1.0

        Rules:
        - if the request clearly fits a category , confidence should be 0.8 - 1.0
        - If it's ambiguous but you can guess, confidence  should be 0.5 -0.7
        - If it's nonsensical or unrelated to telecom , use intent='general' with low confidence 

        Call the tool ONCE with your classification. Do Not add commentary.



     """
    return Agent (
        model = model ,
         system_prompt = system_prompt,
         tools =[classify_intent]
    )



CONFIDENCE_THRESHOLD = 0.6


def llm_classify(ticket_text:str)-> tuple:
    """Use LLM to classify ambigous ticket."""
    classification_result.clear()

    agent = build_classifier_agent()
    t= time.time()
    agent(f"Classify this customer ticket: '{ticket_text}'")
    latency = time.time() -t 

    intent = classification_result.get("intent" ,"general")
    confidence = classification_result.get("confidence" , 0.0)
    agent_name = INTENT_TO_AGENT.get(intent, "GeneralSupportAgent")

    return agent_name, confidence, latency


def hybrid_route(ticket: dict) ->dict:
    """
    Route request using the hybrid strategy.

    Returns a dict with routing decision:
      target_agent, method, confidence , latency_ms


    """
    text = ticket['text']
    t_start = time.time()
#  Priority check (business- critical override )
    target = priority_route(text)
    if target:
        latency_ms = (time.time() - t_start) * 1000
        return {
            "target_agent" : target,
            "method" : "priority",
            "confidence" : 1.0,
            "latency_ms" : latency_ms ,
            "reason" :f"Cancellation intent detected"
        }
# Rule based matching 
    target = rule_based_route(text)
    if target:
        latency_ms =(time.time() - t_start) * 1000
        return {
            "target_agent" : target,
            "method" : "rule",
            "confidence" : 1.0,
            "latency_ms" :latency_ms,
            "reason" :f"Keyword match in ticket text",
        }
 # LLM classification ( )
    agent_name , confidence , llm_latency= llm_classify(text)
    latency_ms =(time.time() - t_start) *1000

    if confidence > CONFIDENCE_THRESHOLD:
        return{
            "target_agent" : agent_name,
            "method": "rule",
            "confidence":confidence,
            "latency_ms" : latency_ms ,
            "reason" :f"LLM classified as '{classification_result.get('intent','?')}'"
                    f"(confidence: {confidence:.2f})",


        }
    # fallback 
    return{
        "target_agent" :"GeneralSupportAgent",
        "method" :"fallback",
        "confidence" : confidence,
        "latency_ms" :latency_ms,
        "reason" :f"Low confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}"
                    f"- flagged for human review ",

    }


def build_billing_agent() ->Agent:
    """ Handles billing-related tickets"""

    model = BedrockModel(
        model_id = NOVA_LITE_MODEL,
        reggion_name = AWS_REGION,
        temperature = 1.0,
    )
    system_prompt ="""
    "You are a billing support agent. Your ONLY job:
    1. Call handle_billing with the ticket_id
    2. Report: Billing issue handled for <ticket_id>
    Do NOT add any other commentary.

    """

    @tool
    def handle_billing(ticket_id:str ) ->str:
        """Handle  abilling-related tickets"""
        ticket = next((t for t in TICKETS if t['id'] ==ticket_id),None)
        if not ticket:
            return json.dumps({'error' : f"Ticket {ticket_id} not found "})
        result ={
            "ticket_id" :ticket_id,
            "action":'billing_resolved',
            "resolution":"Account reviewed - adjustments applied if applicable",
            "case_id" :f"BILL- {ticket_id[-3:]} - (int(time.time()) %1000)",
            "status" :"resolved",
        }
        worker_response["result"] = result
        return json.dumps(result, indent = 2)
    
    return Agent(
        model = model ,
        system_prompt = system_prompt,
        tools =[handle_billing],

    )


def build_techical_agent() ->Agent:
    """Handles technical support tickets ."""
    model = BedrockModel(
        model_id = NOVA_LITE_MODEL,
        region_name = AWS_REGION,
        temperature = 0.0
    )

    system_prompt = """
        You are a billing agent in a telecom service provider .Your ROLE IS ONLY to:
        1.Call the handle_technical tool when intent is about biiling
        2. Report result 
    """
    @tool
    def handle_technical(ticket_id:str) ->str:
        """Handle technical support ticket"""

        ticket = next((t for t in TICKETS if t['id'] == ticket_id),None)    
        if not ticket:
            return json.dumps({'error' :f"Ticket {ticket_id} not found"})
        result ={
            "ticket_id" :ticket_id ,
            "action" :"technical_diagnosed",
            "resolution" :"Issue diagnosed - troubleshooting step applies",
            "case_id" :f"TECH -{ticket_id[-3:]} - {int(time.time()) %10000}",
            "status" :"in_progress",

        }
        worker_response['result'] = result
        return json.dumps(result, indent = 2)

    return Agent(
        model =model,
        system_prompt= system_prompt,
        tools =[handle_technical]

    )

def build_retention_agent() ->Agent :
    """Worker : Handles cancellation requests (retention specialists)."""

    model = BedrockModel(
        model_id = NOVA_LITE_MODEL,
        region_name = AWS_REGION,
        temperature =0.0
    )
    system_prompt= """
    You are  a telcom retention agent : You role is ONLY to :
    1. call the handle_retention tools 
    2. Report the result iven by agent 
    """
    @tool
    def handle_retention(ticket_id:str) ->str:
        """Handle  a cancellation request with retention offer."""
        result ={
            "ticket_id" : ticket_id,
            "action":"retention_offer",
            "escalation":"Retention specialist assigned",
            "case_id" :f"RET- {ticket_id[-3:]} - {int(time.time()) %10000}",
            "status":"pending_customer_response",

        }
        worker_response['result'] = result 
        return json.dumps(result, indent =2 )

    return Agent(
        model = model,
        system_prompt = system_prompt,
        tools =[handle_retention]
    )

def build_general_support_agent() ->Agent:
    """Worker : Fallback for unclassifiable tickets."""

    model =BedrockModel(
        model_id = NOVA_LITE_MODEL,
        region_name= AWS_REGION ,
        temperature = 0.0
    )
    @tool
    def handle_general(ticket_id:str)->str:
        """Create a general support ticket (flagged for human review)."""
        result ={
            "ticket_id" :ticket_id,
            "action" :"general_support",
            "ticket_ref":f"GEN -{ticket_id[-3:]} - {int(time.time()) % 10000}",
            "status":"awaiting_human_review",
            "priority" :"normal",
        }
        worker_response ['result'] = result
        return json.dumps(result, indent =2)

    system_prompt= """
    You are a general support agent .Your role  is only to :
    1.call the handle_general tool  
    2.return a report 
    """

    return Agent(
        model = model ,
        system_prompt = system_prompt,
        tools =[handle_general]
    )


AGENT_BUILDERS ={
    "BillingAgent" :  build_billing_agent,
    "TechnicalAgent" :build_techical_agent,
    "RetentionAgent" : build_retention_agent,
    "GeneralSupportAgent" : build_general_support_agent,
}    


def main() :
    print("=" *70)
    print("Telecom Customer Ticket Router ")
    print("Hybrid Routing: Priority + rules + llm + fallback")
    print(" 4  Specialist Agents + 1 Classifier Agent")
    print(" 20 Tickets (8 billing, 6 technical , 2 cancellation , 4 ambiqous )")
    print("="* 70)

    results =[]

    for ticket in TICKETS:
        tkt_id = ticket['id']
        print(f"\n {"-" *70}")
        print(f"Ticket: {tkt_id}")
        print(f" Text :\"{ticket['text'][:65]}\"")
        print(f"  Expected :{ticket['expected_agent']}({ticket['expected_method']})")


        worker_response.clear()
        t_total_start = time.time()

        routing = hybrid_route(ticket)
        target = routing['target_agent']
        method = routing["method"]

        print(f" -> Routed to : {target}({method}, conf: {routing['confidence']:.2f})")

        builder = AGENT_BUILDERS[target]
        exec_time = run_agent_with_retry(
            builder,
            f"Process ticket {tkt_id} ; {ticket['text']}",
        )

        total_time = time.time() -t_total_start
        result_data = worker_response.get("result",{})
        print(f"  {result_data.get('action', '?')} ={result_data.get('status','?')} ({total_time:.1f}s)")


        log_routing_decision(
            ticket_id= tkt_id ,
            input_text= ticket['text'],
            method = method,
            target_agent= target,
            confidence = routing['confidence'],
            latency_ms= routing['latency_ms'],
        )
        expected = ticket['expected_agent']
        correct =(expected in ('LLM-classified',) or target == expected)

        results.append({
            "id" : tkt_id,
            "target":target,
            "method" :method,
            'confidence' : routing['confidence'],
            "expected" :expected,
            "correct" :correct,
            "total_s" :round(total_time,1 )

        })
    print(f"\n {'=' *70}")
    print(" ROUTING EFFECTIVENESS REPORT")
    print(f"{'=' *70}")
    print(f" {'ID:<10'}{'Target':<22}{'Method' :<10} {'Conf.':<7}{'Time':<7} {'Match'}")
    print(f" {'-'*65}")
    
    for r in results:
        match_str ='✔️' if r['correct'] else  '✖️'
        print(f" {r['id']:<10} {r['target']:<22} {r['method']:<10} {r['confidence']:<7.2f}{r['total_s']:<7.1f}{match_str}")
    
    correct_count = sum(1 for r in results if r["correct"])
    print(f"\n  Routing Accuracy: {correct_count}/{len(results)} ({correct_count/len(results)*100:.0f}%)")

    methods = {}
    for r in results:
        m = r['method']
        if m not in methods:
            methods[m] ={"count" :0, total_time :0}
        methods[m]["count"] +=1
        methods [m]["total_time"] +=r['total_s']

    print(f"\n  Method Distribution:")
    print(f"  {'Method':<12} {'Count':<8} {'Pct':<8} {'Avg Time':<10}")
    print(f"  {'─' * 40}")

    for m in ["priority", "rule", "llm", "fallback"]:
        if m in methods:
            info = methods[m]
            pct = info["count"] / len(results) * 100
            avg = info["total_time"] / info["count"]
            print(f"  {m:<12} {info['count']:<8} {pct:<8.0f}% {avg:<10.1f}s")

    agents ={}
    for r in results:
        a= r["target"]
        agents[a] = agents.get(a,0) +1

    print(f"\n  Agent Distribution:")

    for a in["BillingAgent",'TechnicalAgent' ,'RetentionAgent','GeneralSupportAgent']:
        if a in agents:
            print(f" {a :<22} {agents[a]} tickets")


    scan_result = audit_table.scan()
    audit_entries  = scan_result.get("Items" ,[])

    print(f"\n Audit Log: {len(audit_entries)} entries (DynamoDB: {ROUTING_AUDIT_TABLE})")

    print(f"\n  Key Insight: Same hybrid routing pattern, different domain.")
    print(f"  Rules handle 70% cheaply, LLM handles the ambiguous tail,")
    print(f"  priority catches business-critical requests, fallback ensures nothing drops.\n")


if __name__ =="__main__":
    main()
    

            