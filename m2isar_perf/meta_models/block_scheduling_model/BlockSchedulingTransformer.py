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

    def __findSchedulingFunctionByName(self, elements, instr_name):
        element = list(filter(lambda s: s.name == instr_name, elements))
        if len(element) == 0:
            raise RuntimeError(f"BlockSchedulingTransformer: No scheduling instructions found for instruction '{instr_name}'")
        assert len(element) == 1
        return element[0]

    def __findElementBy(self, elements, func, do_assert=True):
        element = list(filter(func, elements))
        if not do_assert:
            return element
        assert len(element) == 1
        return element[0]

    def __generateBlockSchedulingFunction(self, schedVariant_, blockVariant_, blockDesc_:BasicBlockDescription):

        blockFunction = blockVariant_.createSchedulingFunction(blockDesc_.name, self.id_)
        self.id_ = self.id_ + 1

        schedulingFunctions = schedVariant_.getAllSchedulingFunctions()

        # iterate through each instruction in BB
        for block_i in range(0, len(blockDesc_.instructions)):
            block_instr = blockDesc_.instructions[block_i]
            print("  > Merging instruction", block_instr.name)

            # find instruction in scheduling model
            schedulingFunction = self.__findSchedulingFunctionByName(schedulingFunctions, block_instr.name)

            # TODO: resolve "Enter" nodes
            # add all nodes of instruction to block schedule
            for source_node in schedulingFunction.nodes:
                block_node = blockFunction.createNode(f"{source_node.name}_{block_i}")
                block_node.delay = source_node.delay
                block_node.resourceModel = source_node.resourceModel
                # setup in and out edges respectively
                if block_i == 0:
                    block_node.inEdges = source_node.inEdges
                if block_i+1 == len(blockDesc_.instructions):
                    block_node.outEdges = source_node.outEdges

            # only then copy internal corresponding in/out-nodes for each node
            for source_node in schedulingFunction.nodes:
                block_node = self.__findElementBy(blockFunction.nodes, lambda n: n.name == f"{source_node.name}_{block_i}")
                # TODO: is appending to in nodes sufficient?
                for type in ["inNodes"]: #, "outNodes"]:
                    source_dependencies = getattr(source_node, type)
                    for source_dependency in source_dependencies:
                        depndency = self.__findElementBy(blockFunction.nodes, lambda n: n.name == f"{source_dependency.name}_{block_i}")
                        getattr(block_node, type).append(depndency)

            # connect all outgoing static edges of the previous instruction to nodes in the current instruction
            if block_i == 0:
                continue

            prev_block_instr = blockDesc_.instructions[block_i - 1]
            prevSchedulingFunction = self.__findElementBy(schedulingFunctions, lambda n: n.name == prev_block_instr.name)

            # TODO: for some stages it is necessary to look more into the past (e.g. WB stage on CV32) 
            # loop over all nodes of previous instruction
            for prev_source_node in prevSchedulingFunction.nodes:
                prev_block_node = self.__findElementBy(blockFunction.nodes, lambda n: n.name == f"{prev_source_node.name}_{block_i - 1}")
                out_edges = prev_source_node.getAllOutEdges()

                # loop over all outgoing edges in previous instruction
                for out_edge in out_edges:
                    # skip dynamic edges for now
                    if out_edge.dynamic:
                        print("    WARN ", f"Skipping dynamic out edge to '{out_edge.connectorModel.name}'")
                        continue
                    # TODO: check depth
                    if out_edge.depth > 1:
                        print("    WARN ", "Edge with depth > 1 may not be handled correctly!")

                    timingVariable = out_edge.timingVariable.name

                    print("   ", f"attempting to connect '{timingVariable}'...")

                    # find target node in current instruction
                    for current_source_node in schedulingFunction.nodes:
                        current_block_node = self.__findElementBy(blockFunction.nodes, lambda n: n.name == f"{current_source_node.name}_{block_i}")
                        in_edges = current_source_node.getAllInEdges()
                        match = self.__findElementBy(in_edges, lambda e: not e.dynamic and e.timingVariable.name == timingVariable, do_assert=False)
                        if not len(match):
                            continue

                        # add direct node connection
                        print("   ", f"-> connected to '{current_block_node.name}'!")
                        #prev_block_node.outNodes.append(current_block_node)
                        current_block_node.addInNode(prev_block_node)



            
