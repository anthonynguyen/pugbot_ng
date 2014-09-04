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
    def __init__(self, pugID, now, pugbot, server, players, _map, check, pw):
        self.active = True

        self.pugID = pugID
        self.startTime = now
        self.password = pw

        self.pugbot = pugbot
        self.server = server

        self.players = players
        self.size = len(self.players)
        self.ringersNeeded = 0

        self.chosenMap = _map
        self.checkMap = check

        self.abortVotes = []

        self.checkRE = re.compile("mapname\" is:\"" + self.checkMap)

        self.checkThread = threading.Thread(target=self.check_map_end)
        self.checkThread.start()

    def end(self, abort=False):
        self.active = False

        self.server["active"] = False
        self.server["connection"].send("map " + self.checkMap)

        self.pugbot.write_to_database(self, abort)

        if abort:
            self.pugbot.bot.say("\x030,7 PUG #{} has been aborted! "
                                .format(self.pugID))
        else:
            self.pugbot.bot.say("\x030,4 PUG #{} has ended! "
                                .format(self.pugID))

        self.pugbot.cleanup_active()

    def abort(self):
        self.end(True)

    def check_map_end(self):
        time.sleep(10)

        while self.active:
            response = self.server["connection"].send("mapname").strip()
            if self.checkRE.search(response) is not None:
                self.end()
                return

            time.sleep(10)


class QueuedQueue:
    def __init__(self, players, _map):
        self.players = players
        self._map = _map


class PugbotPlugin:
    def __init__(self, bot):
        self.bot = bot

    def startup(self, config):
        if config is None:
            raise RuntimeError("pugbot_ng requires a config file. Make sure "
                               "config/pugbot_ng.json exists in your basebot "
                               "folder, and that it follows proper JSON "
                               "syntax.")

        database, cursor = self.get_database()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS `reports` (
            `id` INTEGER NULL DEFAULT NULL,
            `date` INTEGER NULL DEFAULT NULL,
            `reportedby` TEXT NULL DEFAULT NULL,
            `player` TEXT NULL DEFAULT NULL,
            `reason` TEXT NULL DEFAULT NULL,
            PRIMARY KEY (`id`)
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS `pugs` (
            `id` INTEGER NULL DEFAULT NULL,
            `start` INTEGER NULL DEFAULT NULL,
            `end` INTEGER NULL DEFAULT NULL,
            `map` TEXT NULL DEFAULT NULL,
            `players` TEXT NULL DEFAULT NULL,
            `captains` TEXT NULL DEFAULT NULL,
            `status` TEXT NULL DEFAULT NULL,
            PRIMARY KEY (`id`)
        );
        """)
        database.commit()
        database.close()

        self.Q = []
        self.votes = {}
        self.active = []

        self.queuedQueues = []

        self.maps = config["maps"]
        self.size = config["size"]
        self.checkmap = config["checkmap"]

        self.servers = []
        for s in config["urt_servers"]:
            server = s.copy()
            server["active"] = False
            server["connection"] = RConnection(
                s["host"], s["port"], s["password"])

            self.servers.append(server)


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
        self.bot.registerCommand("needringer", self.cmd_needringer)
        self.bot.registerCommand("ringers", self.cmd_ringers)
        self.bot.registerCommand("active", self.cmd_active)
        self.bot.registerCommand("last", self.cmd_last)

        self.bot.registerCommand("reports", self.cmd_reports, True)
        self.bot.registerCommand("forcestart", self.cmd_forcestart, True)
        self.bot.registerCommand("remove", self.cmd_remove, True)

        self.running = True
        self.ringerSpamThread = threading.Thread(target=self.spam_ringers)
        self.ringerSpamThread.start()

    def shutdown(self):
        self.running = False
        self.queuedQueues = []
        for pug in self.active:
            pug.abort()

    """
    #------------------------------------------#
    #               Miscellaneous              #
    #------------------------------------------#
    """
    
    def get_database(self):
        database = sqlite3.connect(self.bot.basepath +
                                   "/database/pugbot_ng.sqlite")
        return database, database.cursor()

    def spam_ringers(self):
        while self.running:
            self.output_ringers(self.bot.say)
            time.sleep(60)

    def queue_full(self):
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

        s = None
        for server in self.servers:
            if not server["active"] and server["connection"].test():
                s = server
                s["active"] = True
                break

        if s is None:
            self.bot.say("Sorry, there are no servers available right now. "
                         "Once a server frees up, your PUG will start")
            Q = QueuedQueue(self.Q[:], chosenMap)
            self.queuedQueues.append(Q)
            self.Q = []
            self.votes = {}
            return

        self.start_game(s, self.Q, chosenMap)
        self.Q = []
        self.votes = {}

    def start_game(self, s, players, chosenMap):

        now = int(time.time())

        captains = random.sample(players, 2)

        database, cursor = self.get_database()
        cursor.execute(
            "INSERT INTO pugs (start, end, map, players, captains, status) \
            VALUES(?, -1, ?, ?, ?, 'in progress')",
            (now, chosenMap, ", ".join(players), ", ".join(captains)))
        database.commit()
        pugID = cursor.lastrowid
        database.close()

        self.bot.say(
            "\x030,3 Ding ding ding! PUG #{} is starting! The map is {} "
            .format(pugID, chosenMap))
        self.bot.say("\x030,3 The captains are {} and {}! ".format(
            captains[0], captains[1]))
        self.bot.say("\x037 Players: " + ", ".join(players))

        spass = genRandomString(5)
        thisPUG = ActivePUG(pugID, now, self, s, players,
                            chosenMap, self.checkmap, spass)
        self.active.append(thisPUG)

        
        s["connection"].send("set g_password " + spass)

        s["connection"].send("exec {}".format(s["config_file"]))
        s["connection"].send("map ut4_" + chosenMap)
        s["connection"].send("set g_nextmap " + self.checkmap)

        captainString = "Captains are ^1" + " ^7and ^4".join(captains)
        s["connection"].send("set sv_joinmessage \"{}\"".format(captainString))
        s["connection"].send("g_motd \"PUG #{}\"".format(pugID))
        s["connection"].send("sv_hostname \"{} [^2#pugbot-ng^7]\""
                             .format(s["name"]))
        for user in players:
            self.bot.pm(user,
                        ("The PUG is starting: /connect {}:{};" +
                         "password {}").format(s["host"], s["port"], spass))

    def cleanup_active(self):
        self.active = [pug for pug in self.active if pug.active]
        if self.running and self.queuedQueues:
            for server in self.servers:
                if not server["active"] and server["connection"].test():
                    server["active"] = True
                    Q = self.queuedQueues.pop(0)
                    self.start_game(server, Q.players, Q._map)

    def write_to_database(self, pug, aborted):
        database, cursor = self.get_database()
        cursor.execute(
            "UPDATE pugs SET end = ?, status = ? WHERE id = ?",
            (int(time.time()), "aborted" if aborted else "ended", pug.pugID))
        database.commit()
        database.close()

    """
    #------------------------------------------#
    #             Command Helpers              #
    #------------------------------------------#
    """

    def output_ringers(self, f):
        r = False
        for pug in self.active:
            if pug.ringersNeeded:
                r = True
                f("\x037 PUG #{} needs {} ringer{}!"
                  .format(pug.pugID,
                          pug.ringersNeeded,
                          "" if pug.ringersNeeded == 1 else "s"))

        return r

    def remove_user(self, user):
        if user in self.Q:
            self.Q.remove(user)
            self.bot.say("{} was removed from the queue ({}/{})"
                         .format(user, len(self.Q), self.size))

            if user in self.votes:
                self.votes.pop(user)

            return

        remove = -1
        for ind, Q in enumerate(self.queuedQueues):
            if user in Q.players:
                Q.players.remove(user)
                self.bot.say("{} was removed from the ready queue"
                             .format(user))

                if not self.Q:
                    self.Q = Q.players[:]
                    self.votes = {}
                    self.bot.say("The queue was reset. "
                                 "Please find another player.")
                    remove = ind
                    break
                else:
                    graduate = self.Q.pop(0)
                    Q.players.append(graduate)
                    if graduate in self.votes:
                        self.votes.pop(graduate)
                    self.bot.say("{} was moved to the ready queue."
                                 .format(graduate))
        
        if remove > -1:
            del self.queuedQueues[remove]

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
        return datetime.datetime.fromtimestamp(
            int(float(time))).strftime("%Y-%m-%d %H:%M")

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

        for Q in self.queuedQueues:
            if old in Q.players:
                Q.players.remove(old)
                Q.players.append(new)

    """
    #------------------------------------------#
    #                Commands                  #
    #------------------------------------------#
    """

    def cmd_join(self, issuedBy, data):
        """- joins the queue"""
        for pug in self.active:
            if issuedBy in pug.players:
                self.bot.reply("You are already in an active PUG, please " +
                               "go finish your game before joining another")
                return

        if data.strip().lower() == "ringer":
            for pug in self.active:
                if pug.ringersNeeded:
                    pug.ringersNeeded -= 1
                    self.bot.pm(issuedBy, "Thanks for ringing! "
                                          "Here are the server details:")
                    self.bot.pm(issuedBy, "/connect {}:{}; password {}"
                                          .format(pug.server["host"],
                                                  pug.server["port"],
                                                  pug.password))
                    return

            self.bot.reply("There are no ringers needed right now")
            return

        if issuedBy not in self.Q:
            self.Q.append(issuedBy)
            self.bot.say("{} joined the queue ({}/{})"
                         .format(issuedBy, len(self.Q), self.size))
        else:
            self.bot.reply("You are already in the queue")

        self.vote_helper(issuedBy, data)

        if len(self.Q) == self.size:
            self.queue_full()

    def cmd_leave(self, issuedBy, data):
        """- leaves the queue"""
        for Q in self.queuedQueues:
            if issuedBy in Q.players:
                self.remove_user(issuedBy)
                return

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
        player = data[0].lower()
        reason = " ".join(data[1:])

        dayAgo = time.time() - 86400

        database, cursor = self.get_database()

        cursor.execute(
            "SELECT * FROM reports WHERE reportedBy == '{}' AND date > {}"
            .format(issuedBy, dayAgo))

        result = cursor.fetchall()
        playerCount = 0

        for row in result:
            if row[3] == player:
                playerCount += 1

        if len(result) > 2:
            self.bot.reply("You cannot report more than three people per day")
            return

        if playerCount:
            self.bot.reply("You cannot report the same person twice per day")
            return

        cursor.execute(
            "INSERT INTO reports(date, reportedby, player, reason) \
            VALUES (?, ?, ?, ?)",
            (int(time.time()), issuedBy, player, reason))
        database.commit()
        database.close()

        self.bot.reply("You reported \x02{}\x02 for '\x02{}\x02'"
                       .format(data[0], " ".join(data[1:])))

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

    def cmd_needringer(self, issuedBy, data):
        """- calls for a ringer"""
        for pug in self.active:
            if issuedBy in pug.players:
                pug.ringersNeeded += 1
                self.bot.say("\x037 {} has requested a ringer for PUG#{}! "
                             .format(issuedBy, pug.pugID))
                return

        self.bot.reply("You can't call for a ringer unless you're in an active"
                       " PUG.")

    def cmd_ringers(self, issuedBy, data):
        """- lists needed ringers"""
        needed = self.output_ringers(self.bot.reply)
        if not needed:
            self.bot.reply("Sorry, no ringers are needed at this time")

    def cmd_active(self, issuedBy, data):
        """- list the currently active PUGs"""
        if not self.active:
            self.bot.reply("There are no currently active PUGs")
            return

        for pug in self.active:
            minutes = int((time.time() - pug.startTime) // 60)

            if minutes == 1:
                s = ""
            else:
                s = "s"

            self.bot.reply("\x030,3 PUG #{}     Started: {} minute{} ago     "
                           "Map: {} \x03 "
                           .format(pug.pugID, minutes, s, pug.chosenMap))

    def cmd_last(self, issuedBy, data):
        """- show the last pug that was played"""
        database, cursor = self.get_database()
        pugs = cursor.execute("""
            SELECT * FROM pugs WHERE STATUS != "in progress"
            ORDER BY ID DESC LIMIT 1;""")
        row = cursor.fetchone()
        database.close()

        if not row:
            # lol, this should only ever (possibly) happen once
            self.bot.reply("There is no recently played PUG")
            return

        pugtime = (int(row[2]) - int(row[1])) // 60

        if pugtime == 1:
            s = ""
        else:
            s = "s"

        self.bot.reply("\x030,7 PUG #{}    Lasted: {} minute{}    "
                       "Map: {} \x03".format(row[0], pugtime, s, row[3]))

    """
    #------------------------------------------#
    #              Admin Commands              #
    #------------------------------------------#
    """
    def cmd_reports(self, issuedBy, data):
        """[number] - lists the last n reports"""
        try:
            n = int(data)
        except:
            n = 10

        database, cursor = self.get_database()
        reports = cursor.execute("""
            SELECT * FROM (
                SELECT * FROM `reports` ORDER BY id DESC LIMIT {}
            ) ORDER BY id ASC;
        """.format(n))

        for r in reports:
            self.bot.pm(
                issuedBy,
                "#{} [{}]: {} reported {} for {}"
                .format(r[0], self.time_string(r[1]), r[2], r[3], r[4]))

        database.close()

    def cmd_forcestart(self, issuedBy, data):
        """- starts the game whether there are enough players or not"""
        self.bot.say("{} is forcing the game to start!".format(issuedBy))
        self.queue_full()

    def cmd_remove(self, issuedBy, data):
        """- forcibly removes a user from the queue"""
        if not data:
            self.bot.reply("Specify a user to remove")
            return

        self.remove_user(data.strip())
