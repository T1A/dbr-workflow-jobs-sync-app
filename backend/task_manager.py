import threading

class TaskManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TaskManager, cls).__new__(cls)
                    cls._instance.tasks = {}
        return cls._instance

    def add_task(self, task_id, task_info):
        self._instance.tasks[task_id] = task_info

    def get_task(self, task_id):
        if task_id in self._instance.tasks:
            return self._instance.tasks[task_id]
        else:
            return None

    def update_task(self, task_id, **kwargs):
        if task_id in self._instance.tasks:
            self._instance.tasks [task_id].update(kwargs) 
        else:
            raise KeyError(f"Task with ID {task_id} not found")
