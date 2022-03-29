class LSDTTNetworkTool:
    def __init__(self, input, output, basin_key, export_nodes) -> None:
        self._input = input
        self._output = output
        self._basin_key = basin_key
        self._export_nodes = export_nodes
        self.run_network_tool()

    def run_network_tool(self):
        print(self._input)
        print(self._output)
        print(self._basin_key)
        print(self._export_nodes)