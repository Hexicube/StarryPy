from twisted.internet import reactor
from base_plugin import SimpleCommandPlugin, BasePlugin
from core_plugins.player_manager import permissions, UserLevels
from packets import chat_sent
from utility_functions import give_item_to_player, extract_name
from core_plugins.permission_manager.plugin import perm


class UserCommandPlugin(SimpleCommandPlugin):
    """
    Provides a simple chat interface to the user manager.
    """
    name = "user_management_commands"
    depends = ['command_dispatcher', 'player_manager', 'permission_manager']
    commands = ["who", "whois", "kick", "ban", "give_item", "planet", "mute", "unmute", "passthrough", "shutdown"]
    auto_activate = True

    def activate(self):
        super(UserCommandPlugin, self).activate()
        self.player_manager = self.plugins['player_manager'].player_manager
        self.permission_manager = self.plugins['permission_manager']
        self.godmode = {}

    def who(self, data):
        """Returns all current users on the server. Syntax: /who"""
        who = [w.colored_name(self.config.colors) for w in self.player_manager.who()]
        self.protocol.send_chat_message("%d players online: %s" % (len(who), ", ".join(who)))
        return False

    def planet(self, data):
        """Displays who is on your current planet."""
        who = [w.colored_name(self.config.colors) for w in self.player_manager.who() if
               w.planet == self.protocol.player.planet and not w.on_ship]
        self.protocol.send_chat_message("%d players on your current planet: %s" % (len(who), ", ".join(who)))

    @perm("whois")
    def whois(self, data):
        """Returns client data about the specified user. Syntax: /whois [user name]"""
        name = " ".join(data)
        info = self.player_manager.whois(name)
        if info:
            self.protocol.send_chat_message(
                "Name: %s\nUserlevel: %s\nUUID: %s\nIP address: %s\nCurrent planet: %s""" % (
                    info.colored_name(self.config.colors), UserLevels(info.access_level), info.uuid, info.ip,
                    info.planet))
        else:
            self.protocol.send_chat_message("Player not found!")
        return False

    @perm("kick")
    def kick(self, data):
        """Kicks a user from the server. Usage: /kick [username] [reason]"""
        name, reason = extract_name(data)
        if reason is None:
            reason = "no reason given"
        info = self.player_manager.whois(name)
        if info and info.logged_in:
            tp = self.protocol.factory.protocols[info.protocol]
            tp.die()
            self.protocol.factory.broadcast("%s kicked %s (reason: %s)" %
                                            (self.protocol.player.name,
                                             info.name,
                                             " ".join(reason)))
            self.logger.info("%s kicked %s (reason: %s", self.protocol.player.name, info.name,
                             " ".join(reason))
        return False

    @perm("ban")
    def ban(self, data):
        """Bans an IP (retrieved by /whois). Syntax: /ban [ip address]"""
        ip = data[0]
        self.player_manager.ban(ip)
        self.protocol.send_chat_message("Banned IP: %s" % ip)
        self.logger.warning("%s banned IP: %s", self.protocol.player.name, ip)
        return False

    @perm("ban")
    def bans(self, data):
        """Lists the currently banned IPs. Syntax: /bans"""
        self.protocol.send_chat_message("\n".join(
            "IP: %s " % self.player_manager.bans))

    @perm("ban")
    def unban(self, data):
        """Unbans an IP. Syntax: /unban [ip address]"""
        ip = data[0]
        for ban in self.player_manager.bans:
            if ban.ip == ip:
                self.player_manager.session.delete(ban)
                self.protocol.send_chat_message("Unbanned IP: %s" % ip)
                break
        else:
            self.protocol.send_chat_message("Couldn't find IP: %s" % ip)
        return False

    @perm("give")
    def give_item(self, data):
        """Gives an item to a player. Syntax: /give [target player] [item name] [optional: item count]"""
        if len(data) >= 2:
            name, item = extract_name(data)
            target_player = self.player_manager.get_logged_in_by_name(name)
            target_protocol = self.protocol.factory.protocols[target_player.protocol]
            if target_player is not None:
                if len(item) > 0:
                    item_name = item[0]
                    if len(item) > 1:
                        item_count = item[1]
                    else:
                        item_count = 1
                    give_item_to_player(target_protocol, item_name, item_count)
                    target_protocol.send_chat_message(
                        "%s has given you: %s (count: %s)" % (
                            self.protocol.player.name, item_name, item_count))
                    self.protocol.send_chat_message("Sent the item(s).")
                    self.logger.info("%s gave %s %s (count: %s)", self.protocol.player.name, name, item_name,
                                     item_count)
                else:
                    self.protocol.send_chat_message("You have to give an item name.")
            else:
                self.protocol.send_chat_message("Couldn't find name: %s" % name)
            return False
        else:
            self.protocol.send_chat_message(self.give_item.__doc__)
            
    @perm("mute")
    def mute(self, data):
        """Mute a player. Syntax: /mute [player name]"""
        name = " ".join(data)
        player = self.player_manager.get_logged_in_by_name(name)
        target_protocol = self.protocol.factory.protocols[player.protocol]
        if player is None:
            self.protocol.send_chat_message("Couldn't find name: %s" % name)
            return
        player.muted = True
        target_protocol.send_chat_message("You have been muted.")
        self.protocol.send_chat_message("%s has been muted." % name)

    @perm("mute")
    def unmute(self, data):
        """Unmute a currently muted player. Syntax: /unmute [player name]"""
        name = " ".join(data)
        player = self.player_manager.get_logged_in_by_name(name)
        target_protocol = self.protocol.factory.protocols[player.protocol]
        if player is None:
            self.protocol.send_chat_message("Couldn't find name: %s" % name)
            return
        player.muted = False
        target_protocol.send_chat_message("You have been unmuted.")
        self.protocol.send_chat_message("%s has been unmuted." % name)

    @perm("passthrough")
    def passthrough(self, data):
        """Sets the server to passthrough mode. *This is irreversible without restart.* Syntax: /passthrough"""
        self.config.passthrough = True

    @perm("shutdown")
    def shutdown(self, data):
        """Shutdown the server in n seconds. Syntax: /shutdown [number of seconds] (>0)"""
        x = float(data[0])
        self.protocol.factory.broadcast("SERVER ANNOUNCEMENT: Server is shutting down in %s seconds!" % data[0])
        reactor.callLater(x, reactor.stop)

class MuteManager(BasePlugin):
    name = "mute_manager"
    def on_chat_sent(self, data):
        data = chat_sent().parse(data.data)
        if self.protocol.player.muted and data.message[0] != self.config.command_prefix and data.message[:2] != "##":
            self.protocol.send_chat_message("You are currently muted and cannot speak. You are limited to commands and admin chat (prefix your lines with ## for admin chat.")
            return False
        return True


