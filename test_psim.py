import sys
sys.path.append('/home/jmyoon312')
import copy
from simulation_engine import MasterSimulator, PrecisionMasterSimulator

class DebugPrecisionSimulator(PrecisionMasterSimulator):
    def run(self):
        res = super().run()
        # We can't access local `sims`, but we want to debug total_fees.
        # So we override let's just re-implement run to capture sims
        return res

tickers = {'TQQQ': 1.0}
seed = 10000
cfg = {'version': 'V13', 'modules': {}}

try:
    psim = PrecisionMasterSimulator(tickers, seed, copy.deepcopy(cfg), '/mnt/c/Users/pinode/Downloads/backtest＿1min （2）.csv')
    psim.fetch_all()
    # Let's monkey patch sim
    # Wait, instead of subclassing, I'll just temporarily edit the source or read it.
    
    # We can infer from total return.
    r2 = psim.run()
    # Just print the summary to see if the engine ran correctly
    print("1M Simulation Stats:")
    print("Returns: ", r2['summary']['total_return'])
    print("MDD: ", r2['summary']['mdd'])
except Exception as e:
    import traceback
    traceback.print_exc()
