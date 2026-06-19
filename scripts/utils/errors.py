from discord.ext import commands


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

class ArtistOffline(commands.CommandError):
  """Raised when the local GPU generation server is offline or unreachable"""
  pass

class GenerationDeclined(commands.CommandError):
  """Raised when the image generation request is declined by the artist"""
  pass

class GenerationFailed(commands.CommandError):
  """Raised when the image generation fails on the laptop"""
  pass

class NSFWBlocked(commands.CommandError):
  """Raised when an NSFW prompt is blocked in a SFW channel"""
  pass

class GenerationTimeout(commands.CommandError):
  """Raised when the request times out waiting for approval"""
  pass

