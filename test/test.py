string = 'RVDIA, you ok!'
if string.lower().startswith('rvdia, ') and string.endswith('?') or string.endswith('!'):
    print('success')