import os
import json
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv

class SlackNotifier:
    def __init__(self):
        load_dotenv()
        self.token = os.getenv("SLACK_BOT_TOKEN", "").strip()
        self.channel = os.getenv("SLACK_MANAGER_CHANNEL", "#engineering-manager").strip()
        slack_mock_env = os.getenv("SLACK_MOCK", "false").strip().lower()
        self.mock_mode = (slack_mock_env == "true")
        self.state_file = "mock_slack_messages.json"
        self._init_mock_state()
        
        if self.mock_mode:
            print(f"[MOCK SLACK] Mock active. Logging alerts locally to '{self.state_file}'")
        else:
            print(f"✅ Slack Live Integration Active on {self.channel}")

    def _init_mock_state(self):
        if not os.path.exists(self.state_file):
            with open(self.state_file, "w") as f:
                json.dump([], f, indent=2)

    def _load_mock_state(self) -> list:
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_mock_state(self, state: list):
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error saving mock Slack state: {str(e)}")

    def send_notification(self, text: str, blocks: Optional[List[dict]] = None) -> bool:
        """
        Sends a notification to the Slack manager channel.
        """
        if self.mock_mode:
            state = self._load_mock_state()
            import time
            message = {
                "channel": self.channel,
                "text": text,
                "blocks": blocks,
                "timestamp": time.time()
            }
            state.append(message)
            self._save_mock_state(state)
            print(f"\n📢 [MOCK SLACK ALERT] To: {self.channel}\nMessage: {text}\n")
            return True

        # Live Slack post
        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "channel": self.channel,
            "text": text
        }
        if blocks:
            payload["blocks"] = blocks

        try:
            response = requests.post(url, json=payload, headers=headers)
            res_data = response.json()
            if response.status_code == 200 and res_data.get("ok"):
                print(f"✅ Live Slack Alert posted successfully to {self.channel}")
                # Log live alerts to local state for dashboard display
                state = self._load_mock_state()
                import time
                message = {
                    "channel": self.channel,
                    "text": text,
                    "blocks": blocks,
                    "timestamp": time.time()
                }
                state.append(message)
                self._save_mock_state(state)
                return True
            else:
                print(f"⚠️ Failed to send Slack alert: {res_data.get('error', 'unknown error')} - HTTP status {response.status_code}")
                # Log locally for history feed but return false
                state = self._load_mock_state()
                import time
                state.append({
                    "channel": self.channel,
                    "text": text,
                    "blocks": blocks,
                    "timestamp": time.time(),
                    "status": "failed_live"
                })
                self._save_mock_state(state)
                return False
        except Exception as e:
            print(f"⚠️ Error sending Slack message: {str(e)}")
            state = self._load_mock_state()
            import time
            state.append({
                "channel": self.channel,
                "text": text,
                "blocks": blocks,
                "timestamp": time.time(),
                "status": "failed_exception"
            })
            self._save_mock_state(state)
            return False
            
    def get_messages(self) -> list:
        # Return state regardless of mock/live so the UI always has the feed history
        return self._load_mock_state()
        
    def clear_messages(self) -> bool:
        self._save_mock_state([])
        return True

