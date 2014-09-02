import datetime
import random
import re
import sqlite3
import threading
import time

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
        self.size = len(self.players)
        self.chosenMap = chosenMap
        self.checkMap = checkMap

        self.abortVotes = []

        self.checkRE = re.compile("mapname\" is:\"" + self.checkMap)

        self.checkTimer = threading.Timer(10.0, self.check_map_end)
        self.checkTimer.start()

    def end(self, abort=False):
        self.active = False

        self.server["active"] = False
        self.server["connection"].send("map " + self.checkMap)

        self.checkTimer.cancel()

        self.pugbot.writeToDatabase(self)
        self.pugbot.cleanup_active()

    def abort(self):
        self.pugbot.bot.say("PUG has been aborted")
        self.end(True)

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

        self.database = self.bot.getDatabase()
        self.cursor = self.database.cursor()

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS `reports` (
            `id` INTEGER NULL DEFAULT NULL,
            `date` TEXT NULL DEFAULT NULL,
            `reportedby` TEXT NULL DEFAULT NULL,
            `player` TEXT NULL DEFAULT NULL,
            `reason` TEXT NULL DEFAULT NULL,
            PRIMARY KEY (`id`)
        );
        """)

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
        self.bot.registerCommand("abort", self.cmd_abort)
        self.bot.registerCommand("report", self.cmd_report)

        self.bot.registerCommand("reports", self.cmd_reports, True)
        self.bot.registerCommand("forcestart", self.cmd_forcestart, True)

    def shutdown(self):
        for pug in self.active:
            pug.abort()

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
        self.bot.say("\x030,2The captains are {} and {}!".format(
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
                        ("The PUG is starting: /connect {}:{};" +
                         "password {}").format(s["host"], s["port"], spass))

        self.Q = []
        self.votes = {}

    def cleanup_active(self):
        remove = -1
        for index, pug in enumerate(self.active):
            if not pug.active:
                remove = index

        if remove > -1:
            del self.active[remove]

    def writeToDatabase(self, activePUG):
        self.bot.say("The following players are now allowed " +
                            "to queue up: " + ", ".join(activePUG.players))

    def remove_user(self, user):
        if user in self.Q:
            self.Q.remove(user)
            self.bot.say("{} was removed from the queue".format(user))

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
            self.bot.reply("{} is not a valid map".format(string))
        elif len(mapMatches) > 1:
            self.bot.reply(
                "There are multiple matches for '{}': ".format(string) +
                ", ".join(mapMatches))
        else:
            self.votes[player] = mapMatches[0]
            self.bot.say("{} voted for {}".format(player, mapMatches[0]))

    def time_string(self, time):
        return datetime.datetime.fromtimestamp(int(float(time))).strftime("%Y-%m-%d %H:%M")

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
        """- joins the queue"""
        if issuedBy not in self.Q:
            self.Q.append(issuedBy)
            self.bot.say("{} was added to the queue".format(issuedBy))
        else:
            self.bot.reply("You are already in the queue")

        self.vote_helper(issuedBy, data)

        if len(self.Q) == self.size:
            self.start_game()

    def cmd_leave(self, issuedBy, data):
        """- leaves the queue"""
        if issuedBy in self.Q:
            self.remove_user(issuedBy)
        else:
            self.bot.reply("You are not in the queue")

    def cmd_status(self, issuedBy, data):
        """- displays the status of the current queue"""
        if len(self.Q) == 0:
            self.bot.reply("Queue is empty: 0/{}".format(self.size))
            return

        self.bot.reply("Queue status: {}/{}".format(len(self.Q),
                                                      self.size))
        self.bot.reply(", ".join(self.Q))

    def cmd_maps(self, issuedBy, data):
        """- lists maps that are able to be voted"""
        self.bot.reply("Available maps: " + ", ".join(self.maps))

    def cmd_vote(self, issuedBy, data):
        """- votes for a map"""
        if issuedBy not in self.Q:
            self.bot.reply("You are not in the queue")
        else:
            self.vote_helper(issuedBy, data)

    def cmd_votes(self, issuedBy, data):
        """- shows number of votes per map"""
        if not self.votes:
            self.bot.reply("There are no current votes")
            return

        mapvotes = list(self.votes.values())
        tallies = dict((_map, mapvotes.count(_map)) for _map in mapvotes)

        voteStrings = ["{} ({}): ".format(_map, tallies[_map])
                       for _map in tallies]

        longLen = len(max(voteStrings, key=len))
        voteStrings = ["{} ({}): ".format(_map, tallies[_map])
                                    .ljust(longLen + 1) + "+" * tallies[_map]
                       for _map in tallies]

        for vs in voteStrings:
            self.bot.reply(vs)

    def cmd_report(self, issuedBy, data):
        """[player] [reason] - report a player"""
        if not data:
            return

        data = data.split(" ")
        self.cursor.execute("INSERT INTO reports(date, reportedby, player, reason) VALUES (?, ?, ?, ?)", (time.time(), issuedBy, "".join(data[0]), " ".join(data[1:])))
        self.database.commit()

        self.bot.reply("You reported \x02{}\x02 for '\x02{}\x02'".format(data[0], " ".join(data[1:])))

    def cmd_abort(self, issuedBy, data):
        """- votes to abort a currently-running PUG"""
        for pug in self.active:
            if issuedBy in pug.players:
                target = pug.size // 2 + pug.size % 2
                if issuedBy in pug.abortVotes:
                    self.bot.reply("You have already voted to abort your PUG.")
                else:
                    pug.abortVotes.append(issuedBy)
                    self.bot.say("{} has voted to abort the pug ({}/{})"
                                 .format(issuedBy,
                                         len(pug.abortVotes),
                                         target))

                # Theoretically should never be greater
                    if len(pug.abortVotes) >= target:
                        pug.abort()

    def cmd_reports(self, issuedBy, data):
        """- lists the last 10 reports"""
        reports = self.cursor.execute("""
            SELECT * FROM (
                SELECT * FROM `reports` ORDER BY id DESC LIMIT 10
            ) ORDER BY id ASC;
        """)

        for r in reports:
            self.bot.reply("#{} [{}]: {} reported {} for {}".format(r[0], self.time_string(r[1]), r[2], r[3], r[4]))

    def cmd_forcestart(self, issuedBy, data):
        """- starts the game whether there are enough players or not"""
        self.bot.say("{} is forcing the game to start!".format(issuedBy))
        self.start_game()
