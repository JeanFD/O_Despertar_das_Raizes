class StateMachine:
    def __init__(self, game):
        self.game = game
        self._stack = []

    @property
    def current(self):
        return self._stack[-1] if self._stack else None
    
    def push(self, state):
        if self.current:
            self.current.on_pause()
        self._stack.append(state)
        state.on_enter()

    def pop(self):
        if self.current:
            self.current.on_exit()
            self._stack.pop()
        if self.current:
            self.current.on_resume()

    def change(self, state):
        self.pop()
        self.push(state)

    def handle_event(self, event):
        if self.current:
            self.current.handle_event(event)

    def update(self, dt):
        if self.current:
            self.current.update(dt)
            
    def draw(self, surface):
        # Desenha todas as telas de baixo pra cima
        for state in self._stack:
            state.draw(surface)