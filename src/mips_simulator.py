class mips_simulator:
    def __init__(self, data_list):
        self.data_list = list(data_list)
        self.memory = [1] * 32
        self.registers = [0] + [1] * 31
        self.pipeline = []
        self.branch_taken = False
        self.branch_target = None
        self.skip_next = False
        self.current_pc = 0
        self.next_instruction = None
        self.instructions_to_skip = 0
        self.skipped_instructions = []  # 记录被跳过的指令

    CONTROL_SIGNALS = {
        'lw': {'EX': '01 010 11', 'MEM': '010 11', 'WB': '11'},
        'sw': {'EX': 'X1 001 0X', 'MEM': '001 0X', 'WB': '0X'},
        'beq': {'EX': 'X0 100 0X', 'MEM': '100 0X', 'WB': '0X'},
        'add': {'EX': '10 000 10', 'MEM': '000 10', 'WB': '10'},
        'sub': {'EX': '10 000 10', 'MEM': '000 10', 'WB': '10'}
    }

    def get_control_signals(self, instruction, stage):
        return self.CONTROL_SIGNALS.get(instruction[0], {}).get(stage, '')

    def check_data_hazard(self, inst):
        if inst[0] not in ['add', 'sub', 'beq']:
            return False
        return any(p_inst[0] == 'lw' and p_stage[:2] in ['EX', 'ME'] and 
                  p_inst[1] in [inst[1], inst[2]] for p_inst, p_stage, _, _ in self.pipeline)

    def get_forwarded_value(self, reg):
        for inst, stage, _, result in self.pipeline:
            if stage.startswith("EX") and inst[0] in ['add', 'sub']:
                if result and result[1] == reg:
                    ex_result = self.execute_in_ex(result)
                    if ex_result:
                        return ex_result[2]
        return self.registers[reg]

    def execute_in_id(self, inst):
        op = inst[0]
        if op in ['add', 'sub']:
            rs_val = self.get_forwarded_value(int(inst[2]))
            rt_val = self.get_forwarded_value(int(inst[3]))
            return (op, int(inst[1]), rs_val, rt_val)
        elif op == 'lw':
            addr = self.get_forwarded_value(int(inst[3])) + int(inst[2]) // 4
            return (op, int(inst[1]), addr)
        elif op == 'sw':
            addr = self.get_forwarded_value(int(inst[3])) + int(inst[2]) // 4
            return (op, addr, self.get_forwarded_value(int(inst[1])))
        elif op == 'beq':
            return (op, self.get_forwarded_value(int(inst[1])), 
                   self.get_forwarded_value(int(inst[2])), int(inst[3]))
        return (op, None, None)

    def execute_in_ex(self, result):
        if not result:
            return result
        op = result[0]
        if op == 'add':
            return (op, result[1], result[2] + result[3])
        elif op == 'sub':
            return (op, result[1], result[2] - result[3])
        elif op == 'beq':
            is_equal = result[1] == result[2]
            if is_equal:
                self.branch_taken = True
                self.instructions_to_skip = result[3]
                # 记录要跳过的指令
                start_pc = self.current_pc + 1
                for i in range(self.instructions_to_skip):
                    if start_pc + i < len(self.data_list):
                        self.skipped_instructions.append(self.data_list[start_pc + i])
                # 设置下一条要执行的指令
                next_pc = self.current_pc + result[3] + 1
                if next_pc < len(self.data_list):
                    self.next_instruction = self.data_list[next_pc]
            return (op, is_equal, result[3])
        return result

    def execute_in_mem(self, result):
        if result and result[0] == 'lw':
            return (result[0], result[1], self.memory[result[2]])
        return result

    def write_back(self, result):
        if not result:
            return
        if result[0] in ['add', 'sub', 'lw']:
            self.registers[result[1]] = result[2]
        elif result[0] == 'sw':
            self.memory[result[1]] = result[2]

    def update_pipeline(self):
        new_pipeline = []
        stall_next = any(stage == "ID" and self.check_data_hazard(inst) 
                        for inst, stage, _, _ in self.pipeline)

        # 移除所有被跳过的指令
        current_pipeline = [(inst, stage, stall_count, result) 
                          for inst, stage, stall_count, result in self.pipeline 
                          if inst not in self.skipped_instructions]

        for inst, stage, stall_count, result in current_pipeline:
            if stall_count > 0:
                new_pipeline.append((inst, stage, stall_count - 1, result))
                continue

            if stage == "IF":
                new_stage = "IF" if stall_next else "ID"
                new_pipeline.append((inst, new_stage, 0, None))
            elif stage == "ID":
                if self.check_data_hazard(inst):
                    new_pipeline.append((inst, "ID", 0, None))
                else:
                    result = self.execute_in_id(inst)
                    new_pipeline.append((inst, f"EX {self.get_control_signals(inst, 'EX')}", 0, result))
            elif stage.startswith("EX"):
                result = self.execute_in_ex(result)
                if self.branch_taken and inst[0] == 'beq':
                    if self.next_instruction:
                        new_pipeline.append((self.next_instruction, "IF", 0, None))
                new_pipeline.append((inst, f"MEM {self.get_control_signals(inst, 'MEM')}", 0, result))
            elif stage.startswith("MEM"):
                result = self.execute_in_mem(result)
                new_pipeline.append((inst, f"WB {self.get_control_signals(inst, 'WB')}", 0, result))
            elif stage.startswith("WB"):
                self.write_back(result)

        self.pipeline = new_pipeline
        if self.branch_taken:
            self.instructions_to_skip = 0
        self.skip_next = False

    def run(self):
        cycle = 0
        output = []
        pc = 0
        self.current_pc = 0

        while pc < len(self.data_list) or self.pipeline:
            cycle += 1
            
            if not any(stage == "IF" for _, stage, _, _ in self.pipeline) and pc < len(self.data_list):
                next_inst = self.data_list[pc]
                if not self.branch_taken and next_inst not in self.skipped_instructions:
                    self.pipeline.append((next_inst, "IF", 0, None))
                pc += 1
                self.current_pc = pc - 1

            output.append(f'Cycle {cycle}')
            for inst, stage, _, _ in self.pipeline:
                stage_display = stage.split()[0] if ' ' in stage else stage
                output.append(f'{inst[0]}: {stage if stage_display not in ["IF", "ID"] else stage_display}')

            self.update_pipeline()

            if self.branch_taken and self.branch_target:
                pc += self.branch_target
                self.current_pc = pc - 1
                self.branch_taken = False
                self.branch_target = None
                # 当跳转到新位置时，清除跳过的指令列表
                self.skipped_instructions.clear()

        output.extend([
            f'\n需要{cycle}個週期',
            ' '.join(f'${i}' for i in range(len(self.registers))),
            ' '.join(str(i) for i in self.registers),
            ' '.join(f'W{i}' for i in range(len(self.memory))),
            ' '.join(str(i) for i in self.memory)
        ])
        
        return '\n'.join(output)