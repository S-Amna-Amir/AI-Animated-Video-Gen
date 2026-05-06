import requests
import json

BASE_URL = "http://localhost:8000/api"

# Test data
run_id = "test_run_123"
current_state = {"narrator": "normal", "scene": "bright"}

print("Testing Edit Agent Endpoints\n")

# 1. POST /edit
print("1. POST /edit - 'Make the narrator sound more dramatic'")
data = {
    "run_id": run_id,
    "command": "Make the narrator sound more dramatic",
    "current_state_json": current_state
}
response = requests.post(f"{BASE_URL}/edit", json=data)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}\n")

# Update current_state from response
if response.status_code == 200:
    current_state = response.json()["result"]["updated_state"]

# 2. POST /edit again
print("2. POST /edit - 'The scene looks too bright'")
data = {
    "run_id": run_id,
    "command": "The scene looks too bright",
    "current_state_json": current_state
}
response = requests.post(f"{BASE_URL}/edit", json=data)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}\n")

# 3. GET /history/{run_id}
print("3. GET /history/{run_id}")
response = requests.get(f"{BASE_URL}/history/{run_id}")
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}\n")

# 4. POST /undo
print("4. POST /undo - revert to version 1")
data = {
    "run_id": run_id,
    "version": 1
}
response = requests.post(f"{BASE_URL}/undo", json=data)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}\n")

print("All tests completed!")