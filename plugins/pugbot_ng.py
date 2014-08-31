import random

from pyrcon import RConnection


def genRandomString(length):
    alpha = "abcdefghijklmnopqrstuvwxyz"
    return "".join(random.choice(alpha) for _ in range(length))


class PugbotPlugin:

    def __init__(self, bot):
        self.bot = bot

    def startup(self, config):
        if config is None:
            quit("pugbot_ng requires a config file, make sure" +
                 "config/pugbot_ng.json exists in your basebot folder")

        self.Q = []
        self.votes = {}

        self.maps = config["maps"]
        self.size = config["size"]

        self.servers = []

        for s in config["urt_servers"]:
            with RConnection(s["host"], s["port"], s["password"]) as urtserver:
                self.servers.append({
                    "active": None,
                    "connection": urtserver
                })

        self.bot.say("[pugbot-ng] {} available servers.".format(
            len(self.servers)))

        self.bot.registerEvent("user_part", self.leave_handler)
        self.bot.registerEvent("user_quit", self.leave_handler)
        self.bot.registerEvent("nick_change", self.nick_handler)

        self.bot.registerCommand("join", self.cmd_join)
        self.bot.registerCommand("leave", self.cmd_leave)
        self.bot.registerCommand("status", self.cmd_status)
        self.bot.registerCommand("maps", self.cmd_maps)
        self.bot.registerCommand("vote", self.cmd_vote)
        self.bot.registerCommand("votes", self.cmd_votes)

        self.bot.registerCommand("forcestart", self.cmd_forcestart, True)

    def shutdown(self):
        pass

    """
    #------------------------------------------#
    #             Command Helpers              #
    #------------------------------------------#
    """

    def startGame(self):
        if len(self.Q) < 2:
            self.bot.say("A game cannot be started with fewer than 2 players.")
            return

        mapVotes = list(self.votes.values())

        if not mapVotes:
            mapVotes = self.maps

        maxVotes = max([mapVotes.count(mapname) for mapname in mapVotes])
        mapPool = [mapname for mapname in mapVotes
                   if mapVotes.count(mapname) == maxVotes]

        chosenMap = mapPool[random.randint(0, len(mapPool) - 1)]

        captains = random.sample(self.Q, 2)

        self.bot.say("\x030,2Ding ding ding! The PUG is starting! The map is "
                     + chosenMap)
        self.bot.say("\x030,2The captains are {0} and {1}!".format(
            captains[0], captains[1]))
        self.bot.say("\x037Players: " + ", ".join(self.Q))

        self.Q = []
        self.votes = {}

    def removeUser(self, user):
        if user in self.Q:
            self.Q.remove(user)
            self.bot.say("{0} was removed from the queue".format(user))

        if user in self.votes:
            self.votes.pop(user)

    def resolveMap(self, string):
        matches = []

        if not string:
            return matches

        for m in self.maps:
            if string in m:
                matches.append(m)
        return matches

    def voteHelper(self, player, string):
        mapMatches = self.resolveMap(string)

        if not string:
            return

        if not mapMatches:
            self.bot.reply("{0} is not a valid map".format(string))
        elif len(mapMatches) > 1:
            self.bot.reply(
                "There are multiple matches for '{0}': ".format(string) +
                ", ".join(mapMatches))
        else:
            self.votes[player] = mapMatches[0]
            self.bot.say("{0} voted for {1}".format(player, mapMatches[0]))

    """
    #------------------------------------------#
    #              Event Handlers              #
    #------------------------------------------#
    """

    def leave_handler(self, ev):
        self.removeUser(ev.source.nick)

    def nick_handler(self, ev):
        old = ev.source.nick
        new = ev.target

        if old in self.Q:
            self.Q.remove(old)
            self.Q.append(new)

        if old in self.votes:
            self.votes[new] = self.votes[old]
            self.votes.pop(old)

    """
    #------------------------------------------#
    #                Commands                  #
    #------------------------------------------#
    """

    def cmd_join(self, issuedBy, data):
        """joins the queue"""
        if issuedBy not in self.Q:
            self.Q.append(issuedBy)
            self.bot.say("{0} was added to the queue".format(issuedBy))
        else:
            self.bot.reply("You are already in the queue")

        self.voteHelper(issuedBy, data)

        if len(self.Q) == self.size:
            self.bot.startGame()

    def cmd_leave(self, issuedBy, data):
        """leaves the queue"""
        if issuedBy in self.Q:
            self.removeUser(issuedBy)
        else:
            self.bot.reply("You are not in the queue")

    def cmd_status(self, issuedBy, data):
        """displays the status of the current queue"""
        if len(self.Q) == 0:
            self.bot.reply("Queue is empty: 0/{0}".format(self.size))
            return

        self.bot.reply("Queue status: {0}/{1}".format(len(self.Q),
                                                      self.size))
        self.bot.reply(", ".join(self.Q))

    def cmd_maps(self, issuedBy, data):
        """lists maps that are able to be voted"""
        self.bot.reply("Available maps: " + ", ".join(self.maps))

    def cmd_vote(self, issuedBy, data):
        """votes for a map"""
        if issuedBy not in self.Q:
            self.bot.reply("You are not in the queue")
        else:
            self.voteHelper(issuedBy, data)

    def cmd_votes(self, issuedBy, data):
        """shows number of votes per map"""

        mapvotes = list(self.votes.values())
        tallies = dict((map, mapvotes.count(map)) for map in mapvotes)

        if self.votes:
            for map in tallies:
                self.bot.reply("{0}: {1} vote{2}".format(
                    map, tallies[map], "" if tallies[map] == 1 else "s"))
        else:
            self.bot.reply("There are no current votes")

    def cmd_forcestart(self, issuedBy, data):
        """starts the game whether there are enough players or not"""
        self.bot.say("{0} is forcing the game to start!".format(issuedBy))
        self.startGame()
