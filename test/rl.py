import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sb3_contrib import MaskablePPO
from sts2_rl import STS2CombatEnv
import os

env = STS2CombatEnv()

# if os.path.exists("sts2_ppo.zip"):
#     model = MaskablePPO.load("sts2_ppo", env=env)
#     print("Resuming from saved model.")
# else:
#     model = MaskablePPO("MlpPolicy", env, verbose=1)
#     print("Starting fresh.")
model = MaskablePPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=500_000)
model.save("sts2_ppo")