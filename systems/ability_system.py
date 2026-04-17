class AbilitySystem:
    ABILITIES = ["double_jump", "dash", "wall_jump", "grapple", "high_jump"]

    def __init__(self, game):
        self.game = game
        self.player = None
        game.events.subscribe("item_collected", self.on_item_collected)

    def set_player(self,player):
        self.player = player

    def on_item_collected(self, item_type, **_):
        if item_type in self.ABILITIES and self.player:
            self.player.abilities[item_type] = True
            self.game.events.emit("ability_unlocked", ability=item_type)

    