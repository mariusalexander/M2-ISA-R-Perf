#
# Copyright 2025 Chair of EDA, Technical University of Munich
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

from objprint import op
from meta_models.scheduling_model.SchedulingModel import SchedulingModel
from meta_models.structural_model.StructuralModel import StructuralModel

# wrapper to support dot-notation (see https://stackoverflow.com/questions/2352181/how-to-use-a-dot-to-access-members-of-dictionary)
class dotdict(dict):
    """Allows 'dot.notation' access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

class BasicBlockDescription:
    """Denotes a basic block and its instructions."""

    def __init__(self, name, starting_address=0x0):
        self.name = name
        self.starting_address = starting_address
        self.instructions = []

    def addInstruction(self, instr_name_, rd=None, rs1=None, rs2=None, imm=None):
        instr = { \
            "address": self.starting_address + 4*len(self.instructions),
            "name": instr_name_, \
            "rd":  rd,  \
            "rs1": rs1, \
            "rs2": rs2, \
            "imm": imm  \
        }
        self.instructions.append(dotdict(instr))

class BlockSchedulingTransformer:
    """Transforms a basic block into a block scheudling model. The model only contains the scheduling function for that basic block."""

    def __init__(self):
        self.id_=0;
        pass

    def transform(self, schedulingModel:SchedulingModel, blockDesc:BasicBlockDescription) -> SchedulingModel:

        print ("-- TRANSMFORMER: BLOCK_SCHEDULING_MODEL --")

        blockSchedulingModel = SchedulingModel()

        for variant_i in schedulingModel.getAllVariants():
            print("> Generating block scheduling model for", variant_i.name)

            blockVariant = blockSchedulingModel.createVariant(variant_i.name)
            # TODO: can we simply copy timing variables and external models?
            blockVariant.timingVariables = variant_i.timingVariables
            blockVariant.externalModels  = variant_i.externalModels

            self.__generateBlockSchedulingFunction(variant_i, blockVariant, blockDesc)

        return blockSchedulingModel

    def __generateBlockSchedulingFunction(self, schedVariant_, blockVariant_, blockDesc_:BasicBlockDescription):

        blockFunction = blockVariant_.createSchedulingFunction(blockDesc_.name, self.id_)
        self.id_ = self.id_ + 1

        schedulingFunctions = schedVariant_.getAllSchedulingFunctions()

        # iterate through each instruction in BB
        for block_i in range(0, len(blockDesc_.instructions)):
            block_instr = blockDesc_.instructions[block_i]

            # find instruction in scheduling model
            schedulingFunction = list(filter(lambda s: s.name == block_instr.name, schedulingFunctions))
            if len(schedulingFunction) == 0:
                raise RuntimeError(f"BlockSchedulingTransformer: No scheduling instructions found for instruction '{block_instr.name}'")
            schedulingFunction = schedulingFunction[0]

            # add all nodes of instruction to block schedule
            for node_i in schedulingFunction.nodes:
                node = blockFunction.createNode(f"{node_i.name}_{block_i}")
                node.delay = node_i.delay
                node.resourceModel = node_i.resourceModel
                # setup in and out edges respectively
                if block_i == 0:
                    node.inEdges = node_i.inEdges
                if block_i+1 == len(blockDesc_.instructions):
                    node.outEdges = node_i.outEdges

            # setup instruction-internal in/out nodes
            for node_i in schedulingFunction.nodes:
                node = list(filter(lambda n: n.name == f"{node_i.name}_{block_i}", blockFunction.nodes))
                assert len(node) == 1
                node = node[0]
                for type in ["inNodes", "outNodes"]:
                    nodes = getattr(node_i, type)
                    for node_i in nodes:
                        n = list(filter(lambda n: n.name == f"{node_i.name}_{block_i}", blockFunction.nodes))
                        assert len(n) == 1
                        getattr(node, type).append(n[0])

            # TODO: interconnect nodes of individial instructions

            print(vars(node))
