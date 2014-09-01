import random
import re
import threading

from pyrcon import RConnection


def genRandomString(length):
    alpha = "abcdefghijklmnopqrstuvwxyz"
    return "".join(random.choice(alpha) for _ in range(length))


class ActivePUG:
    def __init__(self, pugbot, server, players, chosenMap, checkMap):
        self.active = True

        self.pugbot = pugbot
        self.server = server

        self.players = players
        self.chosenMap = chosenMap
        self.checkMap = checkMap

        self.checkRE = re.compile("mapname\" is:\"" + self.checkMap)

        self.checkTimer = threading.Timer(10.0, self.check_map_end)
        self.checkTimer.start()

    def writeToDatabase(self):
        self.pugbot.bot.say("The following players are now allowed " +
                            "to queue up: " + ", ".join(self.players))

    def end(self):
        self.active = False
        self.server["active"] = False
        self.writeToDatabase()
        self.pugbot.cleanup_active()

    def abort(self):
        self.checkTimer.cancel()
        self.server["connection"].send("map " + self.checkMap)
        self.end()

    def check_map_end(self):
        response = self.server["connection"].send("mapname").strip()
        if self.checkRE.search(response) is None:
            self.checkTimer = threading.Timer(10.0, self.check_map_end)
            self.checkTimer.start()
        else:
            self.pugbot.bot.say("Map has changed, the PUG is over")
            self.end()


class PugbotPlugin:
    def __init__(self, bot):
        self.bot = bot

    def startup(self, config):
        if config is None:
            quit("pugbot_ng requires a config file, make sure" +
                 "config/pugbot_ng.json exists in your basebot folder")

        self.Q = []
        self.votes = {}
        self.active = []

        self.maps = config["maps"]
        self.size = config["size"]
        self.checkmap = config["checkmap"]

        self.servers = []
        for s in config["urt_servers"]:
            self.servers.append({
                "active": None,
                "connection": RConnection(s["host"], s["port"], s["password"]),
                "host": s["host"],
                "port": s["port"],
                "rcon_password": s["password"]
            })

        # self.bot.say("[pugbot-ng] {} available servers.".format(
        #     len(self.servers)))

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

    def start_game(self):
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

        mine = -1
        for n, s in enumerate(self.servers):
            if not s["active"] and s["connection"].test():
                mine = n
                s["active"] = True

        if mine == -1:
            self.bot.say("No servers available, what a shame... :(")
            self.Q = []
            self.votes = {}
            return

        s = self.servers[mine]

        thisPUG = ActivePUG(self, s, self.Q, chosenMap, self.checkmap)
        self.active.append(thisPUG)

        spass = genRandomString(5)
        s["connection"].send("set g_password " + spass)

        s["connection"].send("exec uzl_ts.cfg")
        s["connection"].send("map " + chosenMap)
        s["connection"].send("set g_nextmap " + self.checkmap)

        captainString = "Captains are " + " and ".join(captains)
        s["connection"].send("set sv_joinmessage \"{}\"".format(captainString))

        for user in self.Q:
            self.bot.pm(user,
                        ("The PUG is starting: /connect {0}:{1};" +
                         "password {2}").format(s["host"], s["port"], spass))

        self.Q = []
        self.votes = {}

    def cleanup_active(self):
        remove = -1
        for index, pug in enumerate(self.active):
            if not pug.active:
                remove = index

        if remove > -1:
            del[remove]

    def remove_user(self, user):
        if user in self.Q:
            self.Q.remove(user)
            self.bot.say("{0} was removed from the queue".format(user))

        if user in self.votes:
            self.votes.pop(user)

    def fuzzy_match(self, string1, string2):
        string1 = string1.lower()
        string2 = string2.lower()

        string1 = re.sub("[_ -]", "", string1)
        string2 = re.sub("[_ -]", "", string2)

        if string1 in string2:
            return True
        
        return False

    def resolve_map(self, string):
        matches = []

        if not string:
            return matches

        for m in self.maps:
            if self.fuzzy_match(string, m):
                matches.append(m)
        return matches

    def vote_helper(self, player, string):
        mapMatches = self.resolve_map(string)

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
        self.remove_user(ev.source.nick)

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

        self.vote_helper(issuedBy, data)

        if len(self.Q) == self.size:
            self.start_game()

    def cmd_leave(self, issuedBy, data):
        """leaves the queue"""
        if issuedBy in self.Q:
            self.remove_user(issuedBy)
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
            self.vote_helper(issuedBy, data)

    def cmd_votes(self, issuedBy, data):
        """shows number of votes per map"""
        if not self.votes:
            self.bot.reply("There are no current votes")
            return

        mapvotes = list(self.votes.values())
        tallies = dict((_map, mapvotes.count(_map)) for _map in mapvotes)

        voteStrings = ["{0} ({1}): ".format(_map, tallies[_map]) 
                       for _map in tallies]

        longLen = len(max(voteStrings, key = len))
        voteStrings = ["{0} ({1}): ".format(_map, tallies[_map])
                                    .ljust(longLen + 1) + "+" * tallies[_map]
                       for _map in tallies]

        for vs in voteStrings:
            self.bot.reply(vs)

    def cmd_forcestart(self, issuedBy, data):
        """starts the game whether there are enough players or not"""
        self.bot.say("{0} is forcing the game to start!".format(issuedBy))
        self.start_game()
