#!/usr/bin/env python3

#
# Copyright 2022 Chair of EDA, Technical University of Munich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import argparse
import pathlib
import pickle
import sys
import os

from common import common as cf

from frontends.corePerfDsl import api as Frontend # TODO: Change from API to Class format

from meta_models.scheduling_model.SchedulingTransformer import SchedulingTransformer
from meta_models.block_scheduling_model.BlockSchedulingTransformer import BlockSchedulingTransformer, BasicBlockDescription, AbiRegisters

from backends.monitor_extractor import api as backend_monitor_extractor # TODO: Change from API to Class format
from backends.structure_viewer.StructuralModelViewer import StructuralModelViewer
from backends.schedule_viewer.SchedulingModelViewer import SchedulingModelViewer
from backends.estimator_generator.EstimatorGenerator import EstimatorGenerator
from backends.basic_block_tester.BasicBlockTestGenerator import BasicBlockTestGenerator
from backends.basic_block_analyzer.DelayGraph import DelayGraphTransformer
from backends.basic_block_analyzer.DelayGraphViewer import DelayGraphViewer
from backends.basic_block_analyzer.DelayAnalyzer import DelayAnalyzer

# Read command line arguments
argParser = argparse.ArgumentParser()
argParser.add_argument("description", help="File containing the description of the performance model.")
argParser.add_argument("-o", "--output_dir", help="Directory to store generated files")
argParser.add_argument("-c", "--code_gen", action="store_true", help="Generate estimator code")
argParser.add_argument("-m", "--monitor_description", action="store_true", help="Generate monitor description")
argParser.add_argument("-i", "--info_print", action="store_true", help="Generate info/debug/doc prints")
argParser.add_argument("-d", "--dump_dir", help="Directory to dump intermediatly generated models.")
argParser.add_argument("-b", "--block_transform", nargs='?', type=argparse.FileType('r'), const=True, help="Basic Block to transform")
argParser.add_argument("--filter", action="store_true", help="Whether to filter out Simple RISCV cores")
args = argParser.parse_args()

# Resolve outDir
outDir = cf.resolveOutDir(args.output_dir, __file__, 1)

filtered_out_cores = False
# Call frontend to generate structural-model
if args.description.endswith('.corePerfDsl'):
    structModel = Frontend.execute(args.description, args.dump_dir)

    if args.filter:
        # TODO: define whitelist/backlist by argument
        # filter out unneeded variants of SimpleRISCV cores
        variants = structModel.variants
        structModel.variants = [ var for var in structModel.variants if "SimpleRISCV" not in var.name or "NoBrPred" in var.name]
        for var in [var for var in variants if var not in structModel.variants]:
            print(f"WARNING: Filtered out variant '{var.name}'!")
            filtered_out_cores = True
else:
    sys.exit("FATAL: Description format is not supported. Currently only supporting files of type .corePerfDsl")

# Call model transformer (structural -> scheduling model) if applicable
if args.code_gen or args.info_print or args.block_transform:
    schedModel = SchedulingTransformer().transform(structModel)

# Call applicable backends
if args.monitor_description:
    backend_monitor_extractor.execute(structModel, outDir)
if args.code_gen:
    EstimatorGenerator().execute(schedModel, outDir)
if args.info_print:
    #StructuralModelViewer().execute(structModel, outDir)
    SchedulingModelViewer().execute(schedModel, outDir)

if args.block_transform is not None:

    descs = []
    r = AbiRegisters()
    verbose = False

    # TODO: only temporary for testing, remove this block
    if args.block_transform is True: # no argument -> load test basic blocks
        desc = BasicBlockDescription("bb_custom_1", 0x100047c)
        desc.addInstruction("addi", rd =r.sp  , rs1=r.sp, imm=(-0x1b0))
        desc.addInstruction("sw"  , rs1=r.s0  , rs2=r.sp)
        desc.addInstruction("sw"  , rs1=r.s1  , rs2=r.sp)
        desc.addInstruction("sw"  , rs1=r.s2  , rs2=r.sp)
        desc.addInstruction("sw"  , rs1=r.s3  , rs2=r.sp)
        desc.addInstruction("sw"  , rs1=r.s4  , rs2=r.sp)
        desc.addInstruction("sw"  , rs1=r.s5  , rs2=r.sp)
        desc.addInstruction("sw"  , rs1=r.s6  , rs2=r.sp)
        desc.addInstruction("sw"  , rs1=r.s7  , rs2=r.sp)
        desc.addInstruction("lui" , rd =r.a0  ,           imm=(0x1800))
        desc.addInstruction("addi", rd =r.a0  , rs1=r.a0, imm=(0x760))
        desc.addInstruction("bge" , rs1=r.zero, rs2=r.a1, imm=(0x1000644)) # implements blez: 0 => a1 <--> a1 <= 0
        descs.append(desc)

        desc = BasicBlockDescription("bb_ppt_example", 0x100047c)
        desc.addInstruction("andi", rd =15, rs1=15)
        desc.addInstruction("slli", rd =15, rs1=15)
        desc.addInstruction("add" , rd =15, rs1=18, rs2=15)
        desc.addInstruction("lw"  , rd =15, rs1=15)
        desc.addInstruction("srli", rd = 8, rs1= 8)
        desc.addInstruction("addi", rd = 9, rs1= 9)
        desc.addInstruction("xor" , rd = 8, rs1=15, rs2= 8)
        desc.addInstruction("bne" , rs1= 9, rs2= 0, imm=8080)
        #desc.addInstruction("andi", rd =15, rs1=15)
        descs.append(desc)

        desc = BasicBlockDescription("bb_addi_add_add", 0x000003c4)
        desc.addInstruction("addi", rd=15, rs1=15, imm=255)
        desc.addInstruction("add" , rd=16, rs1=15, rs2=7)
        desc.addInstruction("add" , rd=15, rs1=15, rs2=16)
        descs.append(desc)

        desc = BasicBlockDescription("bb_lw_addi_sw", 0x000003c4)
        desc.addInstruction("lw"  , rd=3 , rs1=2)
        desc.addInstruction("addi", rd=4, rs1=3, imm=16)
        desc.addInstruction("sw"  , rs1=3, rs2=4)
        descs.append(desc)

        descs = [descs[-3]]

    else:

        print("-- FRONTEND: PARSING BASIC BLOCK --")

        # parse basic block from file
        file = args.block_transform
        filename = os.path.basename(file.name.replace(".txt", ""))
        desc = BasicBlockDescription(filename, int(os.path.splitext(filename)[0], 16))

        file.seek(0)
        for line in file.readlines():
            idx = line.index("#")
            instr_name = line[:idx].strip()
            idx = line.index('[')
            registers = line[idx+1:].replace(']', '').split('|')
            registers = [ tuple(r.strip().split("=")) for r in registers]
            desc.addInstruction(instr_name, **{r[0]:int(r[1]) for r in registers if r[0]})
        descs.append(desc)

    # TODO: temporary sanity checks
    for desc in descs:
        idx = 0
        for instr in desc.instructions:
            match instr.name:
                # meta instructions
                case "mret" | "call" | "ret" | "ecall":
                    raise RuntimeError(f"Cannot handle {instr.name}!")
                # branch and jump instructions
                case "j" | "jal" | "jalr" | \
                     "beq" | "bne" | "blt" | "bltu" | "bge" |  "bgeu":
                    # only last instruct may be a branch
                    if idx < len(desc.instructions) - 1:
                        print(f"WARNING: basic block '{desc.name}' contains multiple branches (istr. no. {idx} is {instr.name})!")
            idx += 1
    descs = [desc for desc in descs if len(desc.instructions) > 0]

    blockSchedule = BlockSchedulingTransformer(verbose=verbose).transform(schedModel, descs)
    if args.code_gen:
        BasicBlockTestGenerator().execute(schedModel, blockSchedule, descs, outDir)
    if args.info_print:
        SchedulingModelViewer().execute(blockSchedule, outDir, cluster=False)
    delayModel = DelayGraphTransformer(verbose=verbose).transform(blockSchedule, unroll_delays=False)
    #DelayGraphViewer().execute(delayModel, outDir)
    DelayAnalyzer(structModel, delayModel) \
        .assume_registers_available() \
        .assume_no_dynamic_delays() \
        .assume_pc_available() \
        .assume_perfect_pipeline() \
        .resolve(estimate_cpi=True)
