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

# TODO: remove me, for debugging purpose only
from objprint import op

import copy
from typing import List, Dict
from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, StaticEdge

# wrapper to support dot-notation 
# (see https://stackoverflow.com/questions/2352181/how-to-use-a-dot-to-access-members-of-dictionary)
class dotdict(dict):
    """Allows using 'dot.notation' to access dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

class AbiRegisters:
    """Maps RISC-V ABI registers onto actual register numbers."""

    def __init__(self):
        self.zero = 0
        self.ra   = 2
        self.sp   = 2
        self.gp   = 3
        self.tp   = 4
        self.t0   = 5
        self.t1   = 6
        self.t2   = 7
        self.s0   = 8
        self.s1   = 9
        self.a0   = 10
        self.a1   = 11
        self.a2   = 12
        self.a3   = 13
        self.a4   = 14
        self.a5   = 15
        self.a6   = 16
        self.a7   = 17
        self.s2   = 18
        self.s3   = 19
        self.s4   = 20
        self.s5   = 21
        self.s6   = 22
        self.s7   = 23
        self.s8   = 24
        self.s9   = 25
        self.s10  = 26
        self.s11  = 27
        self.t3   = 28
        self.t4   = 29
        self.t5   = 30
        self.t6   = 31

class BasicBlockDescription:
    """Denotes a basic block and its instructions."""

    def __init__(self, name, starting_address=0x0):
        self.name = name
        self.starting_address = starting_address
        self.instructions = []

    def addInstruction(self, instr_name, rd=None, rs1=None, rs2=None, imm=None):
        instr = dotdict({
            "address": self.starting_address + (4 * len(self.instructions)),
            "name": instr_name,
            "rd"  : rd,
            "rs1" : rs1,
            "rs2" : rs2,
            "imm" : imm,
            # RV32 and CVA6 specific
            "Xd"  : rd,
            "Xa"  : rs1,
            "Xb"  : rs2,
            # CVA6 clobberModel specific
            "Cb_in" : rd,
            "Cb_out" : rd,
        })
        self.instructions.append(instr)

class BlockSchedulingTransformer:
    """Block Scheduling Transformer"""

    def __init__(self):
        self._id=1024
        # whether to use more descriptive names for edges to registers, like 'r2 (Xa)' instead of 'Xa' 
        self._rename_edges = True 
        self._register_count   = 32
        self._register_models  = ["regModel", "clobberModel"]
        self._target_register_mapping = {
            "regModel" : "Xd",
            "clobberModel": "Cb_in",
        }
        self._branch_prediction_models  = ["staBranchPredModel", "dynBranchPredModel"]
        self._supported_models = self._register_models + self._branch_prediction_models
        
    def transform(self, sched_model:SchedulingModel, block_descriptions:List[BasicBlockDescription]) -> SchedulingModel:
        """
        Transforms basic blocks (BB) into a block scheudling model.
        The model is a regular Scheduling Model which only contains a scheduling function for each BB.
        """
        print ("-- TRANSMFORMER: BLOCK_SCHEDULING_MODEL --")

        blockSchedulingModel = SchedulingModel()
        
        # iterate over each variant
        for sched_variant in sched_model.getAllVariants():
            print(f"> Generating block scheduling model for '{sched_variant.name}'")

            block_variant = blockSchedulingModel.createVariant(sched_variant.name)

            # simply copy over timing variables and external models
            block_variant.timingVariables = copy.deepcopy(sched_variant.timingVariables)
            block_variant.externalModels  = copy.deepcopy(sched_variant.externalModels)

            # iterate over each BB
            for block_desc in block_descriptions:
                self._block_desc = block_desc
                self.__generateBlockSchedulingFunction(sched_variant, block_variant, block_desc)

        self._block_desc = None
        return blockSchedulingModel

    def __generateBlockSchedulingFunction(self, sched_variant:Variant, block_variant:Variant, block_desc:BasicBlockDescription):
        """
        """
        print(f" > Generating block scheduling function for '{block_desc.name}'...")

        # create block scheudling function
        block_function = block_variant.createSchedulingFunction(block_desc.name, self._id)
        self._id += 1

        # helper struct to resolve external and internal edges 
        mappings = dotdict({
            # mappings for timing variables
            "timingVariables": {
                timing_var.name: [ None for _ in range(timing_var.getNumElements()) ] 
                    for timing_var in block_variant.getAllTimingVariables()
            }
        })
        # mappings for register models
        for reg_model in self._register_models:
            mappings[reg_model] = { reg:None for reg in range(0, self._register_count) }

        sched_functions = sched_variant.getAllSchedulingFunctions()

        # iterate over each instruction in the BB
        for block_idx in range(0, len(block_desc.instructions)):
            block_instr = block_desc.instructions[block_idx]
            print(f"  > Appending instruction '{block_instr.name}'...")

            # find instruction of BB in base scheduling model and append nodes to block function
            sched_function = self.__findSchedulingFunctionByName(sched_functions, block_instr.name)
            print(sched_function.identifier)
            self.__appendSchedulingFunction(sched_function, block_function, block_idx)
            self.__resolveInternalEdges(sched_function, block_function, block_idx, mappings)

        op("[FINAL] Timing Variables:", { var:[ n.name if n else None for n in mappings.timingVariables[var] ] for var in mappings.timingVariables})
        op("[FINAL] Register Mapping:", { reg: mappings.regModel[reg].name if mappings.regModel[reg] else None for reg in mappings.regModel if mappings.regModel[reg]})
        op("[FINAL] Clobber Mapping: ", { reg: mappings.clobberModel[reg].name if mappings.clobberModel[reg] else None for reg in mappings.clobberModel if mappings.clobberModel[reg]})

        self.__resolveOutgoingEdges(block_function, mappings)

    def __appendSchedulingFunction(self, sched_function:SchedulingFunction, block_function:SchedulingFunction, block_idx:int):
        """
        Appends all nodes of `sched_function` to `block_function`.
        All properties of each node are copied over.
        """
        # add all nodes of instruction to the block schedule
        for source_node in sched_function.nodes:
            block_node = block_function.createNode(f"{source_node.name}_{block_idx}")
            # apply properties
            self.__copyNode(source_node, block_node)

        # once all nodes are appended, we can setup in/out-nodes for each node
        for source_node in sched_function.nodes:
            block_node = self.__findNode(block_function, block_idx, source_node)
            for source_dependency in source_node.inNodes:
                dependency = self.__findNode(block_function, block_idx, source_dependency)
                dependency.connectNode(block_node)

        # setup root and end node respectively
        if block_idx == 0 and sched_function.getRootNode():
            root_node = self.__findNode(block_function, block_idx, sched_function.getRootNode())
            print(f"  > Setting root node: '{root_node.name}'")
            block_function.setRootNode(root_node)
            
        assert not sched_function.endNode, "It is assumed, that `SchedulingFunction.endNode` is not used"

    def __resolveInternalEdges(self, sched_function:SchedulingFunction, block_function:SchedulingFunction, block_idx:int, mappings):
        for source_node in sched_function.nodes:
            block_node = self.__findNode(block_function, block_idx, source_node)
            # in edges
            for edge in source_node.inEdges:
                if not edge.isDynamic():
                    # static edge
                    assert edge.timingVariable, "Expected static edges to timing variables only!"
                    self.__resolveTimingVariableInEdge(block_node, edge, mappings.timingVariables)
                    continue
                # dynamic edge
                assert edge.connectorModel, "Expected dynamic edges to connector models only!"
                connector_model = edge.connectorModel.name
                if connector_model in self._register_models:
                    self.__resolveRegisterInEdge(block_node, edge, block_idx, mappings, connector_model)
                    continue
                if connector_model in self._branch_prediction_models:
                    self.__resolveBranchPredictionInEdge(block_node, edge, block_idx, connector_model)
                    continue
                assert False, f"Ingoing edge to '{connector_model}' is not handeld!"
            # out edges
            for edge in source_node.outEdges:
                if not edge.isDynamic():
                    # static edge
                    assert edge.timingVariable, "Expected static edges to timing variables only!"
                    self.__resolveTimingVariableOutEdge(block_node, edge, mappings.timingVariables)
                    continue
                # dynamic edge
                assert edge.connectorModel, "Expected dynamic edges to connector models only!"
                connector_model = edge.connectorModel.name
                if connector_model in self._register_models:
                    self.__resolveRegisterOutEdge(block_node, edge, block_idx, mappings, connector_model)
                    continue
                if connector_model in self._branch_prediction_models:
                    self.__resolveBranchPredictionOutEdge(block_node, edge, block_idx, connector_model)
                    continue
                assert False, f"Outgoing edge to '{connector_model}' is not handeld!"

    def __resolveOutgoingEdges(self, block_function:SchedulingFunction, mappings):
        self.__resolveOutgoingTimingVariables(mappings)
        self.__resolveOutgoingRegisters(mappings)

    def __resolveTimingVariableInEdge(self, block_node:Node, edge:StaticEdge, mappings):
        timing_variable = edge.timingVariable.name
        history = mappings[timing_variable]
        assert edge.depth > 0, f"Expected ingoing edges to have a depth > 1 (actual depth: {in_edge.depth})!"
        assert len(history) >= edge.depth, f"Edge exceeds capacity of timing variable '{timing_variable}' (expected {len(history)} vs. depth {edge.depth})"

        last_node = history[edge.depth - 1]
        if not last_node:
            block_node.createStaticInEdge(timing_variable, edge.depth) # append edge
            return
        print (f"   > Resolved timing variable: Node '{block_node.name}' links to '{last_node.name}' ({timing_variable}[{edge.depth}])")
        last_node.connectNode(block_node)

    def __resolveTimingVariableOutEdge(self, block_node:Node, edge:StaticEdge, mappings):
        timing_variable = edge.timingVariable.name
        history = mappings[timing_variable]
        assert edge.depth == 1, f"Expected outgoing edges to have a depth == 1 (acutal depth: {out_edge.depth})!"

        print (f"   > Resolved timing variable: Node '{block_node.name}' sets '{timing_variable}'")
        mappings[timing_variable] = [block_node] + history[:-1] # right-shift history

    def __resolveOutgoingTimingVariables(self, mappings):
        for timing_variable in mappings.timingVariables:
            history = mappings.timingVariables[timing_variable]
            for idx in range(0, len(history)):
                last_node = history[idx]
                if not last_node:
                    continue
                edge = last_node.createStaticOutEdge(timing_variable)
                # TODO: we need to properly support depth > 1 for outgoing edges
                edge.depth = idx + 1

    def __resolveRegisterInEdge(self, block_node:Node, edge:StaticEdge, block_idx:int, mappings, model:str):
        instr = self._block_desc.instructions[block_idx]
        registers  = mappings[model]
        registerNo = instr[edge.name]
        last_node  = registers[registerNo]
        if not last_node:
            print (f"   > Resolved {model}: Node '{block_node.name}' uses 'r{registerNo} ({edge.name})'")
            edge_name = f"r{registerNo} ({edge.name})" if self._rename_edges else edge.name
            block_node.createDynamicInEdge(edge_name, model) # append edge
            return
        print (f"   > Resolved {model}: Node '{block_node.name}' uses 'r{registerNo} ({edge.name})' set by '{last_node.name}'")
        last_node.connectNode(block_node)

    def __resolveRegisterOutEdge(self, block_node:Node, edge:StaticEdge, block_idx:int, mappings, model:str):
        instr = self._block_desc.instructions[block_idx]
        assert edge.name == self._target_register_mapping[model], f"'{edge.name}' was not recognized as a target register (e.g. Xd, Rd, ...)"
        registers  = mappings[model]
        registerNo = instr[edge.name]
        print (f"   > Resolved register: Node '{block_node.name}' sets 'r{registerNo} ({edge.name})'")
        registers[registerNo]  = block_node

    def __resolveOutgoingRegisters(self, mappings):
        for model in self._register_models:
            mapping = mappings[model]
            for registerNo in mapping:
                block_node = mapping[registerNo]
                assert not (block_node and registerNo == 0), f"r0 (zero) should not be used set!"
                if block_node:
                    target_register = self._target_register_mapping[model]
                    print (f"   > Resolved register: Node '{block_node.name}' outputs 'r{registerNo} ({target_register})' ({model})")
                    edge_name = f"r{registerNo} ({target_register})" if self._rename_edges else target_register
                    block_node.createDynamicOutEdge(edge_name, model)

    def __resolveBranchPredictionInEdge(self, block_node:Node, edge:StaticEdge, block_idx:int, model:str):
        if block_idx == 0:
            block_node.createDynamicInEdge(edge.name, model)

    def __resolveBranchPredictionOutEdge(self, block_node:Node, edge:StaticEdge, block_idx:int, model:str):
        instructions = self._block_desc.instructions
        if block_idx == len(instructions) - 1 and self.__isBranchInstruction(instructions[block_idx]):
            block_node.createDynamicOutEdge(edge.name, model)

    def __isBranchInstruction(self, instr):
        # TODO: refine solution (annoate in corePerfDsl?)
        # check if instructions starts with 'b' (sufficient for RISC-V Integer ISA?)
        return instr.name[0] == 'b' 

    def __findElementByName(self, elements, name, error_str = ""):
        element = list(filter(lambda e: e.name == name, elements))
        assert len(element) == 1, error_str
        return element[0]

    def __findSchedulingFunctionByName(self, elements, instr_name) -> SchedulingFunction :
        return self.__findElementByName(elements, instr_name, f"BlockSchedulingTransformer: No scheduling instructions found for instruction '{instr_name}'")

    def __findNode(self, block_function:SchedulingFunction, block_idx:int, source_node:Node) -> Node :
        return self.__findElementByName(block_function.nodes, f"{source_node.name}_{block_idx}")

    def __copyNode(self, source_node:Node, block_node:Node):
        # apply delay
        block_node.delay = source_node.delay
        # link resource model
        if source_node.resourceModel:
            block_node.resourceModel = block_node.parentVariant.getResourceModel(source_node.resourceModel.name)
        # copy edges
        for in_edge in source_node.getAllInEdges():
            if in_edge.isDynamic():
                assert in_edge.connectorModel, "Expected dynamic edges to connector models only!"
                assert in_edge.connectorModel.name in self._supported_models, f"Connector model '{in_edge.connectorModel.name}' is not yet supported, supported are: {self._supported_models}"
            else:
                assert in_edge.timingVariable, "Expected static edges to timing variables only!"
                assert in_edge.depth > 0, f"Expected ingoing edges to have a depth > 1, depth: {in_edge.depth}!"

        for out_edge in source_node.getAllOutEdges():
            if out_edge.isDynamic():
                assert out_edge.connectorModel, "Expected dynamc edges to connector models only!"
                assert out_edge.connectorModel.name in self._supported_models, f"Connector model '{out_edge.connectorModel.name}' ist not yet supported, supported are: {self._supported_models}"
            else:
                assert out_edge.timingVariable, "Expected static edges only to timing variables only!"
                assert out_edge.depth == 1, f"Expected outgoing edges to have a depth == 1, depth: {out_edge.depth}!"
