class mips_simulator:
    def __init__(self, data_list):
        self.data_list = list(data_list)
        self.memory = [1] * 32
        self.registers = [0] + [1] * 31
        self.pipeline = []
        self.branch_taken = False
        self.branch_target = None
        self.skip_next = False
        self.skipped_instructions = []  # 记录被跳过的指令
        self.pc = 0

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
        elif op == 'beq' and result[1] == result[2]:
            self.branch_target = self.beq_position + result[3] + 1
            self.skipped_instructions = self.data_list[self.beq_position + 1:self.branch_target]
            self.branch_taken = True
        return result

    def execute_in_mem(self, result):
        return (result[0], result[1], self.memory[result[2]]) if result and result[0] == 'lw' else result

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

        for inst, stage, stall_count, result in self.pipeline:
            if stall_count > 0:
                new_pipeline.append((inst, stage, stall_count - 1, result))
                continue

            if stage.startswith("EX") and inst[0] == 'beq':
                result = self.execute_in_ex(result)
                if self.branch_taken:
                    new_pipeline = [(i, f"MEM {self.get_control_signals(inst, 'MEM')}", 0, result) if i == inst 
                                  else (i, "ID", 0, None) for i, s, c, r in self.pipeline 
                                  if i == inst or (i not in self.skipped_instructions and s == "IF")]
                    break
            elif stage == "IF":
                new_pipeline.append((inst, "ID" if not stall_next else "IF", 0, None))
            elif stage == "ID" and not self.check_data_hazard(inst):
                new_pipeline.append((inst, f"EX {self.get_control_signals(inst, 'EX')}", 0, self.execute_in_id(inst)))
            elif stage == "ID":
                new_pipeline.append((inst, "ID", 0, None))
            elif stage.startswith("EX"):
                new_pipeline.append((inst, f"MEM {self.get_control_signals(inst, 'MEM')}", 0, self.execute_in_ex(result)))
            elif stage.startswith("MEM"):
                new_pipeline.append((inst, f"WB {self.get_control_signals(inst, 'WB')}", 0, self.execute_in_mem(result)))
            elif stage.startswith("WB"):
                self.write_back(result)

        self.pipeline = new_pipeline
        self.branch_taken = False

    def run(self):
        cycle = 0
        output = []
        while self.pc < len(self.data_list) or self.pipeline:
            cycle += 1
            
            # 检查是否需要添加新指令到 IF
            if not any(stage == "IF" for _, stage, _, _ in self.pipeline) and self.pc < len(self.data_list):
                next_inst = self.data_list[self.pc]
                if next_inst not in self.skipped_instructions:
                    self.pipeline.append((next_inst, "IF", 0, None))
                    if next_inst[0] == 'beq':
                        self.beq_position = self.pc
                self.pc += 1

            # 检查是否有 beq 在 EX 阶段
            has_beq_in_ex = any(stage.startswith("EX") and inst[0] == 'beq' 
                               for inst, stage, _, _ in self.pipeline)

            if has_beq_in_ex:
                # 如果有 beq 在 EX，先执行再输出
                self.update_pipeline()
                if not self.pipeline and self.pc >= len(self.data_list):
                    cycle -= 1
                    break
            else:
                # 正常情况：先输出当前状态，再执行
                if not self.pipeline and self.pc >= len(self.data_list):
                    cycle -= 1
                    break

            # 记录当前周期状态
            output.append(f'Cycle {cycle}')
            for inst, stage, _, _ in sorted(self.pipeline, key=lambda x: 0 if x[1] != "IF" else 1):
                stage_display = stage.split()[0] if ' ' in stage else stage
                output.append(f'{inst[0]}: {stage if stage_display not in ["IF", "ID"] else stage_display}')

            if not has_beq_in_ex:
                # 正常情况：在输出后执行
                self.update_pipeline()

        return '\n'.join(output + [
            f'\n需要{cycle}個週期',
            ' '.join(f'${i}' for i in range(len(self.registers))),
            ' '.join(str(i) for i in self.registers),
            ' '.join(f'W{i}' for i in range(len(self.memory))),
            ' '.join(str(i) for i in self.memory)
        ])