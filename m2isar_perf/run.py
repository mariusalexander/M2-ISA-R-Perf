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
from objprint import op

from common import common as cf

from frontends.corePerfDsl import api as Frontend # TODO: Change from API to Class format

from meta_models.scheduling_model.SchedulingTransformer import SchedulingTransformer
from meta_models.block_scheduling_model.BlockSchedulingTransformer import BlockSchedulingTransformer, BasicBlockDescription, AbiRegisters

from backends.monitor_extractor import api as backend_monitor_extractor # TODO: Change from API to Class format
from backends.structure_viewer.StructuralModelViewer import StructuralModelViewer
from backends.schedule_viewer.SchedulingModelViewer import SchedulingModelViewer
from backends.estimator_generator.EstimatorGenerator import EstimatorGenerator
from backends.basic_block_tester.BasicBlockTestGenerator import BasicBlockTestGenerator
from backends.basic_block_analyzer.DelayGraph import DelayGraph

# Read command line arguments
argParser = argparse.ArgumentParser()
argParser.add_argument("description", help="File containing the description of the performance model.")
argParser.add_argument("-o", "--output_dir", help="Directory to store generated files")
argParser.add_argument("-c", "--code_gen", action="store_true", help="Generate estimator code")
argParser.add_argument("-m", "--monitor_description", action="store_true", help="Generate monitor description")
argParser.add_argument("-i", "--info_print", action="store_true", help="Generate info/debug/doc prints")
argParser.add_argument("-d", "--dump_dir", help="Directory to dump intermediatly generated models.")
argParser.add_argument("-b", "--block_transform", action="store_true", help="Basic Block to transform")
args = argParser.parse_args()

# Resolve outDir
outDir = cf.resolveOutDir(args.output_dir, __file__, 1)

# Call frontend to generate structural-model
if args.description.endswith('.corePerfDsl'):
    structModel = Frontend.execute(args.description, args.dump_dir)
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
if args.block_transform:

    print(args.block_transform)

    r = AbiRegisters()

    descs = []
    """
    desc = BasicBlockDescription("combo_bb_1", 0x100047c)
    desc.addInstruction("addi", rd =r.sp , rs1=r.sp, imm=(-0x1b0))
    desc.addInstruction("sw"  , rs1=r.s0 , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s1 , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s2 , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s3 , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s4 , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s5 , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s6 , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s7 , rs2=r.sp)
    desc.addInstruction("lui" , rd =r.a0 , imm=(0x1800))
    desc.addInstruction("addi", rd =r.a0 , rs1=r.a0, imm=(0x760))
    desc.addInstruction("bge" , rs1=r.zero, rs2=r.a1, imm=(0x1000644)) # implements blez: 0 => a1 <--> a1 <= 0
    descs.append(desc)

    desc = BasicBlockDescription("combo_addi_add_add", 0x000003c4)
    desc.addInstruction("addi", rd=15, rs1=15, imm=255)
    desc.addInstruction("add" , rd=16, rs1=15, rs2=7)
    desc.addInstruction("add" , rd=15, rs1=15, rs2=16)
    descs.append(desc)
    """
    desc = BasicBlockDescription("combo_lw_addi_sw", 0x000003c4)
    desc.addInstruction("lw"  , rd=3 , rs1=2)
    #desc.addInstruction("addi", rd=4, rs1=3, imm=16)
    #desc.addInstruction("sw"  , rs1=3, rs2=4)
    descs.append(desc)

    blockSchedule = BlockSchedulingTransformer().transform(schedModel, descs)
    if args.code_gen:
        BasicBlockTestGenerator().execute(schedModel, blockSchedule, descs, outDir)
    if args.info_print:
        SchedulingModelViewer().execute(blockSchedule, outDir, cluster=False)
    DelayGraph().transform(blockSchedule)