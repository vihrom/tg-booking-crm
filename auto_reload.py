import sys
import time
from subprocess import Popen

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class ReloadHandler(FileSystemEventHandler):
    def __init__(self, bot_script):
        self.bot_script = bot_script
        self.process = None

    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            print(f"Изменение файла {event.src_path}. Перезапуск бота...")
            self.restart_bot()

    def restart_bot(self):
        if self.process:
            self.process.terminate()

        self.process = Popen([sys.executable, self.bot_script])


def start_bot_with_hot_reload(bot_script):
    event_handler = ReloadHandler(bot_script)
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=True)
    observer.start()

    event_handler.restart_bot()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    bot_script = "main.py"
    start_bot_with_hot_reload(bot_script)
