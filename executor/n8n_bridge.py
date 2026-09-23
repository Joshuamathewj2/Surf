"""
executor/n8n_bridge.py
Webhook bridge for n8n to handle complex API integrations.
"""
import requests
from agent.speaker import speak

N8N_WEBHOOK_URL = "http://localhost:5678/webhook/" # Update with your n8n base url if different

def trigger_n8n(workflow_slug: str, payload: dict):
    print(f"[n8n] Triggering workflow: {workflow_slug}")
    url = f"{N8N_WEBHOOK_URL}{workflow_slug}"
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"[n8n OK] Status: {response.status_code}")
        speak(f"Triggered workflow {workflow_slug}")
    except Exception as e:
        print(f"[n8n Error] {e}")
        speak(f"Failed to trigger {workflow_slug}")
