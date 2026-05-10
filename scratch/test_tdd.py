
import re

def split_reward_string(rewards: list):
    """
    Parses a list of reward strings like ['exp+100', 'cns+50', 'krm-10']
    Returns a list of values: [exp, coins, karma]
    """
    res = {"exp": 0, "cns": 0, "krm": 0}
    for r in rewards:
        if '+' in r:
            parts = r.split('+')
            res[parts[0]] = int(parts[1])
        elif '-' in r:
            parts = r.split('-')
            res[parts[0]] = -int(parts[1])
    
    return [res["exp"], res["cns"], res["krm"]]

def test_rewards():
    test_cases = [
        (["exp+12000", "cns+5000", "krm+300"], [12000, 5000, 300]),
        (["exp+500", "krm-50"], [500, 0, -50]),
        (["cns+100"], [0, 100, 0]),
        ([], [0, 0, 0])
    ]
    
    for rewards, expected in test_cases:
        result = split_reward_string(rewards)
        assert result == expected, f"Failed: {rewards} -> {result} (Expected {expected})"
    print("✅ split_reward_string tests passed!")

def mock_func_converter_logic(func: str, user1_stats, user2_stats, user1_hp, user2_hp, max_hp1, max_hp2, is_user1=True):
    # Simplified version of the actual logic
    func = re.sub(r'\(|\)', '', func)
    if '+' in func:
        parts = func.split('+')
        op = '+'
    else:
        parts = func.split('-')
        op = '-'
    
    cmd = parts[0]
    val_str = parts[1]
    is_percent = val_str.endswith('%')
    
    if cmd == 'HP':
        amount = round(max_hp1 * (int(val_str[:-1])/100)) if is_percent else int(val_str)
        if op == '+':
            user1_hp += amount
        else: # Vampire
            user1_hp += amount
            user2_hp -= amount
    
    elif cmd == 'ALL':
        val = round(max_hp1 * (int(val_str[:-1])/100)) if is_percent else int(val_str)
        if op == '+':
            for i in range(3): user1_stats[i] += val
        else:
            for i in range(3): user2_stats[i] = max(1, user2_stats[i] - val)
            
    return user1_stats, user2_stats, user1_hp, user2_hp

def test_logic():
    # Test ALL+10%
    stats1 = [100, 100, 100]
    stats2 = [100, 100, 100]
    hp1, hp2 = 500, 500
    mhp1, mhp2 = 1000, 1000
    
    s1, s2, h1, h2 = mock_func_converter_logic("ALL+10%", stats1, stats2, hp1, hp2, mhp1, mhp2)
    assert s1 == [200, 200, 200], f"Failed ALL+10%: {s1}"
    
    # Test ALL-5
    s1, s2, h1, h2 = mock_func_converter_logic("ALL-5", s1, s2, h1, h2, mhp1, mhp2)
    assert s2 == [95, 95, 95], f"Failed ALL-5: {s2}"
    
    print("✅ Logic tests passed!")

if __name__ == "__main__":
    test_rewards()
    test_logic()
