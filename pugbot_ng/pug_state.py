from pyrcon.rcon import RConnection


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

        self.servers = []

        for s in config["urt_servers"]:
            with Rconnection(s["host"], s["port"], s["password"]) as urtserver:
                self.servers.append({
                    "active": False,
                    "connection": urtserver
                })
