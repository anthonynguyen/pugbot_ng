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

        self.server["connection"].send("set g_password " + genRandomString(5))

        if abort:
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
    def __init__(self, players, _map, region, gt):
        self.players = players
        self._map = _map
        self.region = region
        self.gametype = gt


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
            `gametype` TEXT NULL DEFAULT NULL,
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
        self.regions = {}
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
    
        self.bot.registerEvent("user_part", self.leave_handler)
        self.bot.registerEvent("user_quit", self.leave_handler)
        self.bot.registerEvent("nick_change", self.nick_handler)
        self.bot.registerEvent("private_message", self.chat_handler)
        self.bot.registerEvent("public_message", self.chat_handler)

        self.bot.registerCommand("join", self.cmd_join)
        self.bot.registerCommand("add", self.cmd_join)

        self.bot.registerCommand("leave", self.cmd_leave)
        self.bot.registerCommand("quit", self.cmd_leave)
        self.bot.registerCommand("exit", self.cmd_leave)

        self.bot.registerCommand("status", self.cmd_status)
        self.bot.registerCommand("view", self.cmd_status)

        self.bot.registerCommand("maps", self.cmd_maps)

        self.bot.registerCommand("vote", self.cmd_vote)
        self.bot.registerCommand("map", self.cmd_vote)

        self.bot.registerCommand("votes", self.cmd_votes)
        self.bot.registerCommand("abort", self.cmd_abort)
        self.bot.registerCommand("report", self.cmd_report)
        self.bot.registerCommand("needringer", self.cmd_needringer)
        self.bot.registerCommand("ringers", self.cmd_ringers)
        self.bot.registerCommand("active", self.cmd_active)
        self.bot.registerCommand("last", self.cmd_last)
        self.bot.registerCommand("region", self.cmd_region)
        self.bot.registerCommand("servers", self.cmd_servers)
        self.bot.registerCommand("topmaps", self.cmd_topmaps)

        self.bot.registerCommand("reports", self.cmd_reports, True)
        self.bot.registerCommand("forcestart", self.cmd_forcestart, True)
        self.bot.registerCommand("remove", self.cmd_remove, True)
        self.bot.registerCommand("cancelringers", self.cmd_cancelringers,
                                 True)
        self.bot.registerCommand("forcestop", self.cmd_forcestop, True)
        self.bot.registerCommand("ban", self.cmd_ban, True)

        self.running = True
        self.ringerSpamThread = threading.Thread(target=self.spam_ringers)
        self.ringerSpamThread.start()

        self.idleTimes = {}
        self.idleCheckThread = threading.Thread(target=self.check_idlers)
        self.idleCheckThread.start()

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

    _REGIONS = {
        "na": "North America",
        "eu": "Europe",
        "any": "Any"
    }

    _GAMETYPES = {
        "ts": "Team Survivor",
        "ctf": "Capture the Flag",
        "bomb": "Bomb"
    }

    def get_database(self):
        database = sqlite3.connect(self.bot.basepath +
                                   "/database/pugbot_ng.sqlite")
        return database, database.cursor()

    def check_idlers(self):
        while self.running:
            now = time.time()
            removeQueue = []
            idleTimes = list(self.idleTimes.items())
            for user, idle in idleTimes:
                if now - idle > 1200:
                    self.bot.pm(user, "You have been idle for too long, "
                                      "so you've been removed from the queue.")
                    removeQueue.append(user)
                elif now - idle > 1080:
                    self.bot.pm(user, "You have been idle for a while. "
                                      "Please say something to "
                                      "keep your place in the queue.")

            for user in removeQueue:
                self.remove_user(user)

            time.sleep(30)
            

    def spam_ringers(self):
        while self.running:
            self.output_ringers(self.bot.say)
            time.sleep(90)

    def queue_full(self):
        if len(self.Q) < 2:
            self.bot.say("A game cannot be started with fewer than 2 players.")
            return

        mapVotes = [self.votes[x][1] for x in self.votes
                    if self.votes[x][1] is not None]

        if not mapVotes:
            mapVotes = self.maps

        maxVotes = max([mapVotes.count(mapname) for mapname in mapVotes])
        mapPool = [mapname for mapname in mapVotes
                   if mapVotes.count(mapname) == maxVotes]

        chosenMap = mapPool[random.randint(0, len(mapPool) - 1)]

        gtVotes = [self.votes[x][0] for x in self.votes]
        maxVotes = max([gtVotes.count(gt) for gt in gtVotes])
        gtPool = [gt for gt in gtVotes if gtVotes.count(gt) == maxVotes]

        chosenGT = gtPool[random.randint(0, len(gtPool) - 1)]

        regionVotes = list(self.regions.values())
        numNA = regionVotes.count("na")
        numEU = regionVotes.count("eu")
        numANY = regionVotes.count("any")

        maxRegion = max([numNA, numEU, numANY])

        if numNA == numEU:
            chosenRegion = "any"
        elif maxRegion == numNA:
            chosenRegion = "na"
        elif maxRegion == numEU:
            chosenRegion = "eu"
        else:
            chosenRegion = "any"

        s = None
        for server in self.servers:
            if (not server["active"] and server["connection"].test() and
                    (chosenRegion == "any" or
                     chosenRegion == server["region"])):
                s = server
                s["active"] = True
                break

        if s is None:
            self.bot.say("Sorry, there are no{} servers available right now. "
                         "Once one frees up, your PUG will start"
                         .format(""if chosenRegion == "any" else
                                 " " + self._REGIONS[chosenRegion]))
            Q = QueuedQueue(self.Q[:], chosenMap, chosenRegion, chosenGT)
            self.queuedQueues.append(Q)
            self.Q = []
            self.votes = {}
            self.regions = {}
            self.idleTimes = {}
            return

        self.start_game(s, self.Q, chosenMap, chosenGT)
        self.Q = []
        self.votes = {}
        self.regions = {}
        self.idleTimes = {}

    def start_game(self, s, players, chosenMap, gametype):

        now = int(time.time())

        captains = random.sample(players, 2)

        database, cursor = self.get_database()
        cursor.execute(
            "INSERT INTO pugs (start, end, gametype,\
                               map, players, captains, status) \
            VALUES(?, -1, ?, ?, ?, ?, 'in progress')",
            (now, gametype, chosenMap, ", ".join(players), ", ".join(captains)))
        database.commit()
        pugID = cursor.lastrowid
        database.close()

        self.bot.say(
            "\x030,3 Ding ding ding! PUG #{} is starting on {} ({})! "
            "The game will be {} on {} "
            .format(pugID, s["name"], self._REGIONS[s["region"]],
                    self._GAMETYPES[gametype], chosenMap))
        self.bot.say("\x030,3 The captains are {} and {}! ".format(
            captains[0], captains[1]))
        self.bot.say("\x037 Players: " + ", ".join(players))

        spass = genRandomString(5)
        thisPUG = ActivePUG(pugID, now, self, s, players,
                            chosenMap, self.checkmap, spass)
        self.active.append(thisPUG)

        s["connection"].send("set g_password " + spass)

        s["connection"].send("exec {}".format(s["config_file"][gametype]))
        s["connection"].send("set g_motd \"PUG #{}\"".format(pugID))
        captainString = "Captains are ^1" + " ^7and ^4".join(captains)
        s["connection"].send("set sv_joinmessage \"{}\"".format(captainString))
        s["connection"].send("sv_hostname \"^7{} [^6#pugbot-ng^7]\""
                             .format(s["name"]))

        s["connection"].send("map ut4_" + chosenMap)
        s["connection"].send("set g_nextmap " + self.checkmap)

        for user in players:
            self.bot.pm(user,
                        ("The PUG is starting: /connect {}:{};" +
                         "password {}").format(s["host"], s["port"], spass))

    def cleanup_active(self):
        self.active = [pug for pug in self.active if pug.active]
        if self.running and self.queuedQueues:
            toRemove = []
            for i in range(len(self.queuedQueues)):
                for server in self.servers:
                    region = self.queuedQueues[i].region
                    if (not server["active"] and server["connection"].test()
                            and (region == "any" or
                                 region == server["region"])):
                        server["active"] = True
                        Q = self.queuedQueues[i]
                        toRemove.append(i)
                        self.start_game(server, Q.players, Q._map, Q.gametype)

            for i in toRemove[::-1]:
                self.queuedQueues.pop(i)

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
            if random.randrange(0, 100) < 5:
                self.bot.say("{} ragequit like a baby! ({}/{})"
                         .format(user, len(self.Q), self.size))
            else:
                self.bot.say("{} was removed from the queue ({}/{})"
                         .format(user, len(self.Q), self.size))
    
            # We're being super defensive here
            if user in self.regions:
                del self.regions[user]

            # Here too
            if user in self.idleTimes:
                del self.idleTimes[user]

            if user in self.votes:
                del self.votes[user]

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
        explicitGametype = False
        parts = string.split(" ")
        gametype = "ts"
        for part in parts:
            if part.lower() in self._GAMETYPES:
                explicitGametype = True
                gametype = part.lower()
                parts.remove(part)
                string = " ".join(parts)
                break
        
        if player not in self.votes:
            self.votes[player] = [gametype, None]

        if explicitGametype and gametype != self.votes[player][0]:
            self.votes[player][0] = gametype

        mapMatches = self.resolve_map(string)

        if not mapMatches:
            if explicitGametype:
                self.bot.say("{} voted for {}"
                             .format(player, self._GAMETYPES[gametype]))

            if string:
                self.bot.reply("{} is not a valid map".format(string))
        elif len(mapMatches) > 1:
            if explicitGametype:
                self.bot.say("{} voted for {}"
                             .format(player, self._GAMETYPES[gametype]))

            self.bot.reply(
                "There are multiple matches for '{}': ".format(string) +
                ", ".join(mapMatches))
        else:
            self.votes[player][1] = mapMatches[0]
            if explicitGametype:
                self.bot.say("{} voted for {} on {}"
                             .format(player, self._GAMETYPES[gametype],
                                     mapMatches[0]))
            else:
                self.bot.say("{} voted for {}".format(player, mapMatches[0]))

    def find_active_pug(self, string):
        try:
            num = int(string)
        except:
            return None

        for pug in self.active:
            if num == pug.pugID:
                return pug
        
        return None

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

        if old in self.idleTimes:
            self.idleTimes[new] = self.idleTimes[old]
            del self.idleTimes[old]

        if old in self.votes:
            self.votes[new] = self.votes[old]
            del self.votes[old]

        for Q in self.queuedQueues:
            if old in Q.players:
                Q.players.remove(old)
                Q.players.append(new)

        for pug in self.active:
            if old in pug.players:
                pug.players.remove(old)
                pug.players.append(new)

    def chat_handler(self, ev):
        if ev.source.nick in self.idleTimes:
            self.idleTimes[ev.source.nick] = time.time()

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
            parts = [p.lower() for p in data.split(" ")]
            if "na" in parts:
                region = "na"
                parts.remove("na")
            elif "eu" in parts:
                region = "eu"
                parts.remove("eu")
            else:
                region = "any"

            data = " ".join(parts)

            self.Q.append(issuedBy)
            
            self.regions[issuedBy] = region
            self.idleTimes[issuedBy] = time.time()

            self.bot.say("{} joined the queue{} ({}/{})"
                         .format(issuedBy,
                                 " from " + self._REGIONS[region]
                                 if region != "any" else "",
                                 len(self.Q),
                                 self.size))
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
        for ind, Q in enumerate(self.queuedQueues):
            self.bot.reply(
                "Waiting list {}{} ({} on {}): {}"
                .format(ind + 1,
                        "" if Q.region == "any" else " - " +
                        self._REGIONS[Q.region],
                        self._GAMETYPES[Q.gametype],
                        Q._map, ", ".join(Q.players)))

        if len(self.Q) == 0:
            self.bot.reply("Current queue is empty (0/{})".format(self.size))
            return

        self.bot.reply("Current queue ({}/{}): {}"
                       .format(len(self.Q), self.size, ", ".join(self.Q)))

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
        if not self.Q:
            self.bot.reply("The queue is empty")
            return

        self.bot.reply("\x032Regions:")
        regionVotes = list(self.regions.values())
        for r in ["any", "eu", "na"]:
            if regionVotes.count(r):
                num = regionVotes.count(r)
                self.bot.reply("{} {}".format(
                    "{} ({}): ".format(r, num).ljust(11), "+" * num))

        self.bot.reply("\x033Gametypes:")
        gtVotes = [self.votes[x][0] for x in self.votes]

        tallies = dict((gt, gtVotes.count(gt)) for gt in gtVotes)
        voteStrings = ["{} ({}): ".format(self._GAMETYPES[gt], tallies[gt])
                       for gt in tallies]

        longLen = len(max(voteStrings, key=len))
        voteStrings = ["{} ({}): ".format(self._GAMETYPES[gt], tallies[gt])
                       .ljust(longLen + 1) + "+" * tallies[gt]
                       for gt in tallies]

        for vs in voteStrings:
            self.bot.reply(vs)

        mapvotes = [self.votes[x][1] for x in self.votes if
                    self.votes[x][1] is not None]
        if not mapvotes:
            self.bot.reply("There are no current map votes")
            return

        tallies = dict((_map, mapvotes.count(_map)) for _map in mapvotes)

        voteStrings = ["{} ({}): ".format(_map, tallies[_map])
                       for _map in tallies]

        longLen = len(max(voteStrings, key=len))
        voteStrings = ["{} ({}): ".format(_map, tallies[_map])
                       .ljust(longLen + 1) + "+" * tallies[_map]
                       for _map in tallies]

        self.bot.reply("\x036Maps:")
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

            self.bot.reply("\x030,3 PUG #{}     Started: {} minute{} ago     "
                           "Map: {} \x03 "
                           .format(pug.pugID, minutes,
                                   "" if minutes == 1 else "s",
                                   pug.chosenMap))

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

        minutes = (int(time.time()) - int(row[1])) // 60

        if minutes > 1440:
            when = "day"
            minutes = (minutes // 60) / 24
        elif minutes > 59:
            when = "hour"
            minutes = minutes // 60
        else:
            when = "minute"

        self.bot.reply("\x030,7 PUG #{}    Ended: {} {}{} ago     "
                       "Map: {}     Type: {} \x03".format(row[0], minutes, when,
                                             "" if minutes == 1 else "s",
                                             row[4], row[3]))

    def cmd_region(self, issuedBy, data):
        """[region] - displays or sets your current region"""
        if issuedBy not in self.Q:
            self.bot.reply("You are not in the queue")

        if not data:
            self.bot.reply("Your current region is: " +
                           self._REGIONS[self.regions[issuedBy]])
            return

        rawdata = data
        data = data.strip().lower()
        if data in ["any", "na", "eu"]:
            self.regions[issuedBy] = data
            self.bot.reply("Your region was changed to: " +
                           self._REGIONS[data])
        else:
            self.bot.reply("'{}' is not a valid region".format(rawdata))

    def cmd_servers(self, issuedBy, data):
        """- lists servers"""
        ss = ["{} ({}):".format(s["name"], self._REGIONS[s["region"]])
              for s in self.servers]
        longLen = len(max(ss, key=len))

        for s in self.servers:
            self.bot.reply(
                "{} {}"
                .format("{} ({}):"
                        .format(s["name"], self._REGIONS[s["region"]])
                        .ljust(longLen),
                        "\x033 Online\x03 ({}\x03)"
                        .format("\x034In use" if s["active"] else "\x033Free")
                        if s["connection"].test() else "\x034 Offline"))

    def cmd_topmaps(self, issuedBy, data):
        """- show the top 5 played maps"""
        database, cursor = self.get_database()
        stats = cursor.execute(
            "SELECT map, count(map) FROM pugs \
            GROUP by map ORDER by count(map) DESC LIMIT 5;")
        row = stats.fetchall()
        database.close()

        row = [list(row) for row in row]
        self.bot.reply("Top maps: " +
                       ", ".join(["{} ({})".format(r[0], r[1]) for r in row]))
        
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

    def cmd_cancelringers(self, issuedBy, data):
        """- cancels the ringer requests for a game"""
        pug = self.find_active_pug(data)

        if pug is None:
            self.bot.reply("'{}' is not a valid PUG number".format(data))
            return

        pug.ringersNeeded = 0
        self.bot.reply("Ringer requests cleared for PUG #{}".format(pug.pugID))

    def cmd_forcestop(self, issuedBy, data):
        """- stops an active game"""
        pug = self.find_active_pug(data)

        if pug is None:
            self.bot.reply("'{}' is not a valid PUG number".format(data))
            return

        pug.abort()

    def cmd_ban(self, issuedBy, data):
        """[host] [length] ([reason]) - ban a player from the channel for x time"""
        if not data:
            self.bot.reply("Not enough parameters given")
            return

        data = data.split()
        hostmask, length, *reason = data

        self.bot.pm("Q", "TEMPBAN {} *!*@{} {} {}".format(self.bot.channel, hostmask, length, " ".join(reason)))
