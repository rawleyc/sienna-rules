import os
import glob
import json
import yaml
import requests

# 1. Fetch Environment Configurations
KIBANA_URL = os.environ.get("KIBANA_URL").rstrip('/')
API_KEY = os.environ.get("KIBANA_API_KEY")
INTERNAL_CA = os.environ.get("INTERNAL_CA")

# Handle custom enterprise CAs safely on the local runner
ca_verify = True
if INTERNAL_CA:
    ca_path = "internal_ca.crt"
    with open(ca_path, "w") as f:
        f.write(INTERNAL_CA)
    ca_verify = ca_path
else:
    # Turn this to False ONLY if testing isolated labs without certificates 
    ca_verify = False

# 2. Build Rule API Payload
rules_to_sync = []
rule_files = glob.glob('rules/**/*.yaml', recursive=True) + glob.glob('rules/**/*.yml', recursive=True)
ndjson_files = glob.glob('rules/**/*.ndjson', recursive=True)

for file_path in rule_files:
    with open(file_path, 'r') as stream:
        try:
            rule_data = yaml.safe_load(stream)
            rules_to_sync.append(rule_data)
        except yaml.YAMLError as exc:
            print(f"Error parsing YAML file {file_path}: {exc}")

for file_path in ndjson_files:
    with open(file_path, 'r') as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue

            try:
                rule_data = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Error parsing NDJSON file {file_path} on line {line_number}: {exc}")
                continue

            # Kibana exports can include a summary object after the rule objects.
            if isinstance(rule_data, dict) and rule_data.get('name'):
                rules_to_sync.append(rule_data)

if not rules_to_sync:
    print("No rules found to sync.")
    exit(0)

# Kibana 9.5 exposes the Detection Engine create endpoint, but not the
# older bulk-create endpoint. For a custom space, insert "/s/YOUR_SPACE"
# after KIBANA_URL.
rule_url = f"{KIBANA_URL}/api/detection_engine/rules"

headers = {
    "Authorization": f"ApiKey {API_KEY}",
    "kbn-xsrf": "true",
    "Content-Type": "application/json"
}

# 3. Request sync execution
print(f"Syncing {len(rules_to_sync)} rule(s) to self-managed Kibana...")
failed_rules = []

for rule_data in rules_to_sync:
    response = requests.post(
        rule_url,
        headers=headers,
        json=rule_data,
        verify=ca_verify,
    )

    if response.status_code not in [200, 201]:
        failed_rules.append({
            "name": rule_data.get("name", "<unnamed rule>"),
            "status_code": response.status_code,
            "response": response.text,
        })

if failed_rules:
    print(f"Deployment failed for {len(failed_rules)} rule(s):")
    print(json.dumps(failed_rules, indent=2))
    exit(1)

print(f"Successfully deployed {len(rules_to_sync)} rule(s).")
