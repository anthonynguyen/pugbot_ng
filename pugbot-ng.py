#!/usr/bin/env python
import irc.bot

class Pugbot(irc.bot.SingleServerIRCBot):
    cmdPrefixes = "!>.@"
    def __init__(self, server, port, channel, nick):
        super(Pugbot, self).__init__([(server, port)], nick, nick)
        self.channel = channel

    def say(self, msg):
        self.connection.privmsg(self.channel, msg)

    def pm(self, nick, msg):
        self.connection.privmsg(nick, msg)
    
    def on_welcome(self, conn, e):
        conn.join(self.channel)

    def on_privmsg(self, conn, e):
        self.executeCommand(conn, e)

    def on_pubmsg(self, conn, e):
        if (e.arguments[0][0] in self.cmdPrefixes):
            self.executeCommand(conn, e)

    def executeCommand(self, conn, e):
        issuedBy = e.source.nick
        text = e.arguments[0][1:].split(" ")
        command = text[0]
        data = text[1:]

        if command == "hello":
            self.say("Hello, {}!".format(issuedBy))
        elif command == "plzdie":
            self.die("{} doesn't like me :<".format(issuedBy))
        else:
            self.say("I don't understand that command")

if __name__ == "__main__":
    bot = Pugbot("irc.quakenet.org", 6667, "#nuubs", "pugbot-ng")
    bot.start()
