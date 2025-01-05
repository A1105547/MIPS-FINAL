import pathlib, re
from mips_simulator import mips_simulator

output_dir = pathlib.Path(__file__).parent.parent.resolve()/'outputs'
output_dir.mkdir(exist_ok=True)

for test_file in (pathlib.Path(__file__).parent.parent.resolve()/'inputs').glob('*.txt'):
    test_program = open(test_file, 'r').read().splitlines()
    test_program = [list(x for x in re.split('[, $()]+', line) if x) for line in test_program]
    mips = mips_simulator(test_program)
    with open(output_dir/(test_file.stem + '_result.txt'), 'w') as f:
        f.write(mips.run())

