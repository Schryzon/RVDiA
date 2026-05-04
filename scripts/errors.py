from discord.ext import commands

class NotGTechMember(commands.CommandError):
  """Raised when command is not being run by a G-Tech Resman member"""
  pass

class NotInGTechServer(commands.CommandError):
  """Raised when the command was not executed in a G-Tech server"""
  pass

class NotGTechAdmin(commands.CommandError):
  """Raised when the command was not executed by a G-Tech Admin, replaces is_owner()"""
  pass

class NoProfilePicture(commands.CommandError):
  """Raised when the user doesn't have a profile picture (automatically aborts command)"""
  pass

class Blacklisted(commands.CommandError):
    """Raised if user is blacklisted."""
    pass

class NoEventAvailable(commands.CommandError):
  """Raised when no events are currently ongoing"""
  pass

class NotVoted(commands.CommandError):
  """Raised when user hasn't voted on Top.gg"""
  pass

class NoGameAccount(commands.CommandError):
  """Raised when user hasn't created a game account yet"""
  pass

class AccountIncompatible(commands.CommandError):
  """Raised when a Re:Volution account doesn't match the format"""
  pass

class NoPremiumStatus(commands.CommandError):
  """Raised when a user doesn't have premium status"""
  pass
