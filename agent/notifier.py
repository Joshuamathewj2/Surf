"""
agent/notifier.py
Windows Toast notifications using plyer.
"""
from plyer import notification
from agent.speaker import speak

def notify(title: str, message: str, speak_text: bool = True):
    print(f"[Notify] {title}: {message}")
    if speak_text:
        speak(message)
    try:
        notification.notify(
            title=title,
            message=message,
            app_name="Surf AI",
            timeout=5
        )
    except Exception as e:
        print(f"[Notifier Error] {e}")
