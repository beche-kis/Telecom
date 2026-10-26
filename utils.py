import re
import time
import os 
from datetime import datetime, timezone
import boto3 
from strands.models import BedrockModel
from strands import Agent, tool

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")   # All agents use Nova Lite (routing needs speed)


ROUTING_AUDIT_TABLE = os.environ.get("ROUTING_AUDIT_TABLE", "Telecom-routing-audit")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
audit_table = dynamodb.Table(ROUTING_AUDIT_TABLE)


def clean_response(text:str)->str:
    """Strip <thinking>...</thinking> tags from Nova model outputs."""
    return re.sub(r"<thinking>.*?</thinking>\s*", "", str(text), flags = re.DOTALL).strip()

def run_agent_with_retry(agent_builder,prompt:str, max_retries: int = 3)->float:
    """
    Run an agent with retry logic for transient Bedrock errors.
    Uses exponential backoff( 1s,2s, 4s) to handle throttling.
    """

    for attempt in range(max_retries):
        try:
          agent = agent_builder()
          t= time.time()
          agent(prompt)
          return time.time()  -t 
        except Exception as e:
            if attempt < max_retries -1 :
               wait = 2 ** attempt
               print(f" [Retry {attempt +1} /{max_retries}] {e.__class__.__name__},waiting {wait}s...")
               time.sleep(wait)
            else:
               print(f"  [Failed] {e.__class__.__name__} after {max_retries} attempts")
               raise



    

def log_routing_decision(ticket_id:str, input_text:str, method:str,
                         target_agent:str, confidence:float, latency_ms:float):
    """
    Log a routing decision to DynamoDB.
    Table schema(from CloudFormation):
        PK: request_id(S) | SK: timestamp(S)
        Attributes : input_text, routing_method, target_agent, confidence, latency_ms
    """

    entry ={
        "request_id" :ticket_id,
        "timestamp" : datetime.now(timezone.utc).isoformat(),
        "input_text" :input_text[:80],
        "routing_method" : method,
        "target_agent" :target_agent,
        "confidence" :str(confidence).capitalize(),
        "latency_ms" :str(round(latency_ms,1)),
        "tt1" : int(time.time()) + 86400,
    }
    audit_table.put_item(Item = entry)

