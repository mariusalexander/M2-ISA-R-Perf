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

import copy
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
        instr = {
            "address": self.starting_address + 4*len(self.instructions),
            "name": instr_name_,
            "rd"  : rd, 
            "rs1" : rs1,
            "rs2" : rs2,
            "imm" : imm,
            # RV32 specific
            "Xd"  : rd, 
            "Xa"  : rs1, 
            "Xb"  : rs2,
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
            blockVariant.timingVariables = copy.deepcopy(variant_i.timingVariables)
            blockVariant.externalModels  = copy.deepcopy(variant_i.externalModels)

            self.__generateBlockSchedulingFunction(variant_i, blockVariant, blockDesc)

        return blockSchedulingModel

    def __findSchedulingFunctionByName(self, elements, instr_name):
        element = list(filter(lambda s: s.name == instr_name, elements))
        if len(element) == 0:
            raise RuntimeError(f"BlockSchedulingTransformer: No scheduling instructions found for instruction '{instr_name}'")
        assert len(element) == 1
        return element[0]

    def __findElementByName(self, elements, name):
        element = list(filter(lambda e: e.name == name, elements))
        assert len(element) == 1
        return element[0]

    def __generateBlockSchedulingFunction(self, schedVariant_, blockVariant_, blockDesc_:BasicBlockDescription):

        blockFunction = blockVariant_.createSchedulingFunction(blockDesc_.name, self.id_)
        self.id_ = self.id_ + 1

        scheduling_functions = schedVariant_.getAllSchedulingFunctions()

        # iterate through each instruction in BB
        for block_i in range(0, len(blockDesc_.instructions)):
            block_instr = blockDesc_.instructions[block_i]
            print("  > Merging instruction", block_instr.name)

            # find instruction in scheduling model
            schedulingFunction = self.__findSchedulingFunctionByName(scheduling_functions, block_instr.name)

            # TODO: resolve "Enter" nodes
            # add all nodes of instruction to block schedule
            for source_node in schedulingFunction.nodes:
                block_node = blockFunction.createNode(f"{source_node.name}_{block_i}")
                block_node.delay = source_node.delay
                block_node.resourceModel = source_node.resourceModel
                # TODO: set output edges properly
                if block_i+1 == len(blockDesc_.instructions):
                    block_node.outEdges = copy.deepcopy(source_node.outEdges)

            # only then copy internal corresponding in/out-nodes for each node
            for source_node in schedulingFunction.nodes:

                block_node = self.__findElementByName(blockFunction.nodes, f"{source_node.name}_{block_i}")

                # TODO: is appending to in-nodes sufficient?
                source_dependencies = source_node.inNodes
                for source_dependency in source_dependencies:
                    dependency = self.__findElementByName(blockFunction.nodes, f"{source_dependency.name}_{block_i}")
                    block_node.addInNode(dependency)
                
                for in_edge in source_node.inEdges:
                    # dynamic edges
                    if in_edge.dynamic:

                        # skip some dynamic edges for now
                        # TODO: resolve 'regModel' dynamically
                        if in_edge.connectorModel.name != 'regModel':
                            print("    WARN ", f"Skipping dynamic ingoing edge to '{in_edge.connectorModel.name}'")
                            continue

                        register_name = in_edge.name
                        register = block_instr[register_name]

                        print("   ", f"attempting to resolve dynamic ingoing edge to 'r{register}' ({register_name})...")

                        success = False                        
                        for prev_block_i in reversed(range(0, block_i)):
                            prev_block_instr = blockDesc_.instructions[prev_block_i]
                            # check if previous instruction uses register
                            # TODO: differentiate between using/setting register?
                            # TODO: fix this hard-coded mess
                            target_register_name = 'Xd' if prev_block_instr['rd'] == register else 'Xa' if prev_block_instr['rs1'] == register else 'Xb' if prev_block_instr['rs2'] else None
                            if not target_register_name:
                                continue
                            print("   ", f"instr no. {prev_block_i} uses register 'r{register}' in {target_register_name}'")
                            prev_scheduling_function = self.__findSchedulingFunctionByName(scheduling_functions, prev_block_instr.name)
                            for prev_source_node in prev_scheduling_function.nodes:
                                prev_block_node = self.__findElementByName(blockFunction.nodes, f"{prev_source_node.name}_{prev_block_i}")
                                out_edges = prev_source_node.getAllOutEdges()
                                #op(out_edges)
                                out_edges = list(filter(lambda e: e.dynamic and e.name == target_register_name and e.connectorModel.name == 'regModel', out_edges))
                                for out_edge in out_edges:
                                    print("   ", f"-> success, connected to '{prev_block_node.name}'!")
                                    block_node.addInNode(prev_block_node)
                                    success = True
                            if success:
                                break

                        if success:
                            continue

                        print("   ", f"-> failed, adding external edge to register 'r{register}'!")
                        in_edge = copy.deepcopy(in_edge)
                        in_edge.name += f"(r{register})"
                        block_node.inEdges.append(in_edge)
                        continue

                    # static edges
                    # TODO: check depth
                    if in_edge.depth > 1:
                        print("    WARN ", "Edge with depth > 1 may not be handled correctly!")

                    timing_variable = in_edge.timingVariable.name
                    print("   ", f"attempting to connect '{timing_variable}_{block_i}'...")

                    success = False
                    for prev_block_i in reversed(range(0, block_i)):
                        prev_block_instr = blockDesc_.instructions[prev_block_i]
                        prev_scheduling_function = self.__findSchedulingFunctionByName(scheduling_functions, prev_block_instr.name)
                        for prev_source_node in prev_scheduling_function.nodes:
                            prev_block_node = self.__findElementByName(blockFunction.nodes, f"{prev_source_node.name}_{prev_block_i}")
                            out_edges = prev_source_node.getAllOutEdges()
                            out_edges = list(filter(lambda e: not e.dynamic and e.timingVariable.name == timing_variable, out_edges))
                            for out_edge in out_edges:
                                print("   ", f"-> connected to '{prev_block_node.name}'!")
                                block_node.addInNode(prev_block_node)
                                success = True
                        if success:
                            break

                    if success:
                        continue

                    print("   ", f"-> adding external edge!")
                    
                    # edge not found -> most likely an external edge
                    block_node.inEdges.append(in_edge)
 
                # TODO: this is a workaround because we copied all outEdges blindly
                # prune outgoing edges if they are register connections
                block_node.outEdges = [out_edge for out_edge in block_node.outEdges if not (out_edge.dynamic and out_edge.connectorModel.name == 'regModel')]
                
                # add outgoing edges for target registers (rd)
                for out_edge in source_node.outEdges:
                    if not out_edge.dynamic:
                        continue
                        
                    # skip some dynamic edges for now
                    if out_edge.connectorModel.name != 'regModel':
                        print("    WARN ", f"Skipping dynamic outgoing edge to '{out_edge.connectorModel.name}'")
                        continue

                    register_name = out_edge.name
                    if register_name != 'Xd':
                        print("    WARN ", f"Skipping non-target register '{register_name}'")
                        continue
                    register = block_instr[register_name]

                    print("   ", f"attempting to resolve dynamic outgoing edge to 'r{register}' ({register_name})...")

                    success = False   
                      
                    # TODO: always write to regModel if its a target register?
                    if False: 
                        for next_block_i in range(block_i + 1, len(blockDesc_.instructions)):
                            next_block_instr = blockDesc_.instructions[next_block_i]
                            # check if next instruction use register thats being set in this node 
                            # TODO: fix this hard-coded mess
                            target_register_name = 'Xd' if next_block_instr['rd'] == register else None
                            if not target_register_name:
                                continue
                            print("   ", f"-> aborting, instr no. {next_block_i} uses register 'r{register}' in {target_register_name}'")
                            success = True
                            break

                    if success:
                        continue

                    print("   ", f"-> adding external edge to register 'r{register}'!")
                    out_edge = copy.deepcopy(out_edge)
                    out_edge.name += f"(r{register})"
                    block_node.outEdges.append(out_edge)
                    continue



            
