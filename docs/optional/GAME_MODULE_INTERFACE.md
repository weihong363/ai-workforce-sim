# Game Module Interface

Each game module must implement:

class GameModule:

    def get_agents(self):
        pass

    def get_tasks(self):
        pass

    def evaluate(self, output):
        pass

    def compute_reward(self, score):
        pass

    def transform_input(self, asset):
        pass
