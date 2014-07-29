class PugState():

    def __init__(self, config):
        self.server = config["server"]
        self.port = config["port"]

        self.nick = config["nick"]
        self.channel = config["channel"]

        self.cmdPrefixes = config["prefixes"]
        self.owners = config["owners"]
        self.pugSize = config["size"]

        self.password = ""

        self.Q = []
        self.maps = config["maps"]
        self.votes = {}

        self.loggedIn = self.owners
