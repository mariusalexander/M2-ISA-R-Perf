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

import copy
from typing import List, Dict
from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node

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
    """Block Scheduling Transformer helper class."""

    def __init__(self):
        self.id_=0
        pass

    def transform(self, sched_model:SchedulingModel, block_descriptions:List[BasicBlockDescription]) -> SchedulingModel:
        """Transforms basic blocks (BB) into a block scheudling model. The model only contains scheduling function that describe each BB."""
        print ("-- TRANSMFORMER: BLOCK_SCHEDULING_MODEL --")

        blockSchedulingModel = SchedulingModel()

        # iterate over each variant
        for sched_variant in sched_model.getAllVariants():
            print(f"> Generating block scheduling model for {sched_variant.name}")

            block_variant = blockSchedulingModel.createVariant(sched_variant.name)

            # TODO: can we simply copy timing variables and external models?
            block_variant.timingVariables = copy.deepcopy(sched_variant.timingVariables)
            block_variant.externalModels  = copy.deepcopy(sched_variant.externalModels)

            # iterate over each BB
            for block_desc in block_descriptions:
                self.__generateBlockSchedulingFunction(sched_variant, block_variant, block_desc)

        return blockSchedulingModel

    def __generateBlockSchedulingFunction(self, sched_variant:Variant, block_variant:Variant, block_desc:BasicBlockDescription):
        """ """
        print(f" > Generating block scheduling function for '{block_desc.name}'...")

        block_function = block_variant.createSchedulingFunction(block_desc.name, self.id_)
        self.id_ += 1

        # iterate over each instruction in BB
        for block_idx in range(0, len(block_desc.instructions)):
            block_instr = block_desc.instructions[block_idx]
            print(f"  > Appending instruction '{block_instr.name}'...")

            # find instruction of BB in base scheduling model and append nodes to block function
            sched_functions = sched_variant.getAllSchedulingFunctions()
            sched_function = self.__findSchedulingFunctionByName(sched_functions, block_instr.name)
            self.__appendSchedulingFunction(sched_function, block_variant, block_function, block_idx)
            
        # TODO: resolve "Enter" nodes
        self.__resolveEdges(sched_variant, block_function, block_desc)
            
    def __appendSchedulingFunction(self, sched_function:SchedulingFunction, block_variant:Variant, block_function:SchedulingFunction, block_idx:int):
        """ Appends all nodes of `sched_function` to `block_function`. Instructions are not yet interconnected. """
        # add all nodes of instruction to block schedule
        for source_node in sched_function.nodes:
            block_node = block_function.createNode(f"{source_node.name}_{block_idx}")
            # apply properties
            self.__copyNode(source_node, block_node)

        # setup in/out-nodes for each node of the instruction
        for source_node in sched_function.nodes:
            block_node = self.__findNode(block_function, block_idx, source_node)
            for source_dependency in source_node.inNodes:
                dependency = self.__findNode(block_function, block_idx, source_dependency)
                block_node.addInNode(dependency)
                
    def __resolveTimingVariables(self, block_node:Node):
        print("   > Resolving timing variables...")

    def __resolveEdges(self, sched_variant:Variant, block_function:SchedulingFunction, block_desc:BasicBlockDescription):
        print("  > Merging edges...")

        timingVariableMapping = { var:None for var in block_function.parent.getAllTimingVariables()}
        op(timingVariableMapping)

        for block_node in block_function.nodes:
            pass
        """
                for in_edge in block_node.inEdges:
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
                        for prev_block_i in reversed(range(0, block_idx)):
                            prev_block_instr = block_desc.instructions[prev_block_i]
                            # check if previous instruction uses register
                            # TODO: differentiate between using/setting register?
                            # TODO: fix this hard-coded mess
                            target_register_name = 'Xd' if prev_block_instr['rd'] == register else 'Xa' if prev_block_instr['rs1'] == register else 'Xb' if prev_block_instr['rs2'] else None
                            if not target_register_name:
                                continue
                            print("   ", f"instr no. {prev_block_i} uses register 'r{register}' in {target_register_name}'")
                            prev_sched_function = self.__findSchedulingFunctionByName(sched_functions, prev_block_instr.name)
                            for prev_source_node in prev_sched_function.nodes:
                                prev_block_node = self.__findElementByName(block_function.nodes, f"{prev_source_node.name}_{prev_block_i}")
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
                    print("   ", f"attempting to connect '{timing_variable}_{block_idx}'...")

                    success = False
                    for prev_block_i in reversed(range(0, block_idx)):
                        prev_block_instr = block_desc.instructions[prev_block_i]
                        prev_sched_function = self.__findSchedulingFunctionByName(sched_functions, prev_block_instr.name)
                        for prev_source_node in prev_sched_function.nodes:
                            prev_block_node = self.__findElementByName(block_function.nodes, f"{prev_source_node.name}_{prev_block_i}")
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

                    if success:
                        continue

                    print("   ", f"-> adding external edge to register 'r{register}'!")
                    out_edge = copy.deepcopy(out_edge)
                    out_edge.name += f"(r{register})"
                    block_node.outEdges.append(out_edge)
                    continue
"""


            

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
    
    def __findNode(self, block_function:SchedulingFunction, block_idx:int, source_node:Node):
        return self.__findElementByName(block_function.nodes, f"{source_node.name}_{block_idx}")
    
    def __copyNode(self, source_node:Node, block_node:Node):
        # apply properties
        block_node.delay = source_node.delay
        if source_node.resourceModel:
            block_node.resourceModel = block_node.parentVariant.getResourceModel(source_node.resourceModel.name)
        for in_edge in source_node.getAllInEdges():
            if in_edge.isDynamic():
                block_node.createDynamicInEdge(in_edge.name, in_edge.connectorModel.name)
            else:
                block_node.createStaticInEdge(in_edge.timingVariable.name, in_edge.depth)
        for out_edge in source_node.getAllOutEdges():
            if out_edge.isDynamic():
                block_node.createDynamicInEdge(out_edge.name, out_edge.connectorModel.name)
            else:
                block_node.createStaticInEdge(out_edge.timingVariable.name, out_edge.depth)
