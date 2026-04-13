from collections import defaultdict

class EventBus:
    def __init__(self):
        self._listeners = defaultdict(list)

    def subscribe(self, event_type, callback):
        if callback in self._listeners[event_type]:
            self._listeners[event_type].remove(callback)

    def unsubscribe(self, event_type, callback):
        if callback in self._listeners[event_type]:
            self._listeners[event_type].remove(callback)

    def emit(self, event_type, **data):
        for cb in list(self._listeners[event_type]):
            cb(**data)