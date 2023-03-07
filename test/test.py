from scripts.spamhaus import SpamHausChecker

checker = SpamHausChecker()
check = checker.is_spam('https://discoqd.com/newyear')
print(check)