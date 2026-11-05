from datetime import datetime,timedelta,timezone
import random


def records(count=1000,seed=42):
    if type(count) is not int or not 1<=count<=10000:
        raise ValueError('Demo Win for Life da 1 a 10.000 estrazioni')
    rng=random.Random(seed);end=datetime(2025,1,1,tzinfo=timezone.utc)
    return [{'game':'Win for Life','variant':'classico','wheel':'','draw_id':f'SYNTHETIC-WFL-{seed}-{i:06}',
             'occurred_at':(end-timedelta(hours=count-i)).isoformat(),
             'numbers':sorted(rng.sample(range(1,21),10)),'extras':{'numerone':rng.randint(1,20)},
             'synthetic':True,'source':'SYNTHETIC_DEMO_WINFORLIFE'} for i in range(count)]
