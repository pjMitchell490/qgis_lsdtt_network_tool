import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
import numpy as np
import os
import logging

'''
self.logger = logging.getself.logger(__name__)
self.logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
file_handler = logging.FileHandler('lsdtt_network_log2.log')
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
self.logger.addHandler(stream_handler)
self.logger.addHandler(file_handler)
'''



class LSDTTNetworkTool:
    def __init__(self, qgis_dialog, input, output, basin_key, export_nodes) -> None:
        self.qgis_dialog = qgis_dialog
        self._file_input = input
        self._file_output = output
        self._basin_id = basin_key
        # This is a test
        self._export_all_nodes = export_nodes
        self.logger = qgis_dialog.logger

    def run_network_tool(self):
        self.logger.info(self._file_input)
        self.logger.info(self._file_output)
        self.logger.info(self._basin_id)
        self.logger.info(self._export_all_nodes)


        if self._file_output[-5:] != '.gpkg':
            self._file_output += '.gpkg'

        # And give the nodes' output filename if needed
        if self._export_all_nodes:
            file_output_nodes = os.path.splitext(self._file_output)[0] + '_nodes' + '.gpkg'

        self.qgis_dialog.progressBar.setValue(5)

        # Read the LSDTopoTools river chi profile inputs, indexing by the 
        # node index
        rp = pd.read_csv(self._file_input, index_col='NI', na_filter=False) #node changed to NI
        # The "source key" sets the ID for each segment -- section of channel between
        # tributary junctions.
        segment_ids = np.array(list(set(rp['source_key'])))

        # Get the source key for all receiver nodes
        # This will show the upstream limit(s) of confluences, and provide the
        # node IDs of these confluences.
        receiver_nodes_at_mouths = []
        rp.insert(len(rp.columns), 'receiver_source_key', None)
        #for _node in rp.index:
        # IMPORTANT FOR EFFICIENCY: MINIMIZE THE NUMBER OF TIMES YOU UPDATE THE
        # DATAFRAME

        # Limit to a single basin if so desired
        length = rp.index.size
        progress_before_step = 5.0
        progress = progress_before_step
        progress_after_step = 40
        if self._basin_id:
            rp = rp[rp['basin_key'] == self._basin_id]


        _tmplist = []
        for _node in rp.index:
            _receiver_node = rp.loc[_node, 'receiver_NI']
            if _receiver_node in rp.index and _node != _receiver_node:
                _receiver_source_key = rp.loc[_receiver_node, 'source_key']
            else:
                self.logger.info("Found mouth node. Offmap receiver node ID: "
                        + str(_receiver_node))
                _receiver_source_key = -1
                receiver_nodes_at_mouths.append(_receiver_node)
            _tmplist.append(_receiver_source_key)
            progress += (progress_after_step - progress_before_step)/length
            print(progress)
            self.qgis_dialog.progressBar.setValue(progress)
        self.qgis_dialog.progressBar.setValue(progress_after_step)

        rp['receiver_source_key'] = _tmplist

        # In the case of the downstream-most one, no node with this ID will exist
        mouth_nodes = list(rp[rp['receiver_source_key'] == -1].index)



        # Next, identify these confluences by places where the receiver_source_key
        # differs from the source_key
        confluence_downstream_nodes = list(set(list(rp['receiver_NI']
                                                        [rp['source_key'] !=
                                                        rp['receiver_source_key']])))
        # Remove river mouths
        # Inefficient but should be relatively few points at this step.
        confluence_downstream_nodes = np.array(confluence_downstream_nodes)
        for _receiver_node_at_mouth in receiver_nodes_at_mouths:
            confluence_downstream_nodes = confluence_downstream_nodes\
                                            [confluence_downstream_nodes
                                            != _receiver_node_at_mouth]

        self.qgis_dialog.progressBar.setValue(60)

        # Create a set of confluence locations
        confluences = []
        for _node in confluence_downstream_nodes:
            _x = rp.loc[_node, 'longitude']
            _y = rp.loc[_node, 'latitude']
            confluences.append([_x, _y])
        confluences = np.array(confluences)

        # Create a set of river mouth locations
        mouths = []
        for _node in mouth_nodes:
            _x = rp.loc[_node, 'longitude']
            _y = rp.loc[_node, 'latitude']
            mouths.append([_x, _y])
        mouths = np.array(mouths)

        # Obtain channel-head locations
        # They are in another file, but whatever.... reduce data dependencies
        channel_head_nodes = []
        source_keys = list(set(list(rp['source_key'])))
        for _source_key in source_keys:
            channel_head_nodes.append( rp.index[rp['source_key'] == _source_key][0] )
        channel_head_nodes = np.array(channel_head_nodes)

        # Create a list of segment sources
        # This includes all channel heads (true "sources") and confluences
        source_nodes = np.hstack(( channel_head_nodes, confluence_downstream_nodes ))

        # Create a list of segment terminations
        # This includes all confluence and mouth nodes
        termination_nodes = np.hstack(( confluence_downstream_nodes, mouth_nodes ))

        # Create a list of lists of node IDs going down each segment in the network
        # Each segment will include as its downstream-most cell the upstream-most
        # node from the next tributary junction.
        # This is duplicitive, but helpful for network dynamics and plotting
        # line segments that represent the river attributes.
        segments_nodes = []
        for _source_node in source_nodes:
            segment_nodes = [_source_node]
            segment_nodes.append(rp.loc[segment_nodes[-1], 'receiver_NI'])
            while segment_nodes[-1] not in termination_nodes:
                segment_nodes.append(rp.loc[segment_nodes[-1], 'receiver_NI'])
            segments_nodes.append(segment_nodes)

        # Next, reconstruct the data table elements for each of these points
        # within its specific segment in the network
        segments = []
        for segment_nodes in segments_nodes:
            segments.append( rp.loc[segment_nodes, :] )

        # Apply an arbitrary ID in order
        _id = 0
        segment_ids = []
        for segment in segments:
            segment_ids.append(_id)
            segment['segment_id'] = _id
            _id += 1
        segment_ids = np.array(segment_ids)

        # Obtain correlative ID numbers from the source nodes
        internal_segment_ids = []
        for segment in segments:
            internal_segment_ids.append(segment.index[0])
        internal_segment_ids = np.array(internal_segment_ids)

        # Also record which segment they send their flow to
        internal_receiver_segment_ids = []
        for segment in segments:
            internal_receiver_segment_ids.append( segment.index[-1] )
        internal_receiver_segment_ids = np.array(internal_receiver_segment_ids)

        # To-segment IDs
        toseg = []
        for i in range(len(internal_segment_ids)):
            toseg_bool = (internal_receiver_segment_ids[i] == internal_segment_ids)
            if np.sum(toseg_bool) > 1:
                self.logger.info(i)
                self.logger.info(np.sum(toseg_bool))
                self.logger.error("ERROR! NETWORK IS BRANCHING.")
            elif np.sum(toseg_bool) == 0:
                self.logger.info(i)
                self.logger.info(np.sum(toseg_bool))
                self.logger.info("Channel mouth; segment ID -1.")
                toseg.append(-1)
            else:
                toseg.append(int(segment_ids[toseg_bool]))
        toseg = np.array(toseg)

        # Unnecessary, but why not? Makes life easier.
        # Especially once I use these to create the nodes!
        for i in range(len(segments)):
            segment = segments[i]
            segment['toseg'] = internal_receiver_segment_ids[i] # = toseg
            _id += 1

        # Now we have the full set of points that can be written to file.
        # But how about the GIS lines?
        # Let's get more information in each segment.
        # And let's add it to its own DataFrame


        dfsegs = pd.DataFrame({'id': segment_ids, 'toseg': toseg})


        ############################
        # Add mean lat/lon columns #
        ############################

        _out = []
        for segment in segments:
            _out.append( segment['longitude'].mean() )
        dfsegs['longitude (mean)'] = _out

        _out = []
        for segment in segments:
            _out.append( segment['latitude'].mean() )
        dfsegs['latitude (mean)'] = _out


        ###############
        # Add columns #
        ###############

        # Segment slope
        _out = []
        for segment in segments:
            _out.append( (np.max(segment['elevation']) - np.min(segment['elevation'])) /
                        (np.max(segment['flow_distance']) - np.min(segment['flow_distance'])) )
        dfsegs['slope'] = _out

        # Segment elevations:
        _max = []
        _min = []
        _mean = []
        for segment in segments:
            _mean.append(np.mean(segment['elevation']))
            _max.append(np.max(segment['elevation']))
            _min.append(np.min(segment['elevation']))
        dfsegs['z mean'] = _mean
        dfsegs['z_max'] = _max
        dfsegs['z_min'] = _min
            
        # Segment drainage area (mean across segment)
        _out = []
        for segment in segments:
            _out.append(np.mean(segment['drainage_area'])/1E6)
        dfsegs['drainage area (mean) [km2]'] = _out

        # Segment chi (mean across segment)
        _out = []
        for segment in segments:
            _out.append(np.mean(segment['chi']))
        dfsegs['chi'] = _out

        # Segment normalized steepness index, *assuming this = m_chi from LSDTT*
        # (This is true for the default A_0 = 1)
        _out = []
        for segment in segments:
            _out.append(np.mean(segment['chi'])) # changed from m_chi
        dfsegs['ksn'] = _out

        ################################################################
        # Find a way in the future to add custom values to the columns #
        ################################################################

        # These are going to be particular to this case
        #dfsegs['depth_to_bedrock_m'][i] = np.mean(segment['depth_to_bedrock'])
        #dfsegs['bedrock_lithology'] = np.mean(segment['depth_to_bedrock'])


        # Create a set of LineString objects
        stream_lines = []
        for segment in segments:
            stream_lines.append( LineString(
                                    segment.loc[:, ('longitude', 'latitude', 'elevation')].values ) )

        # Now convert to geopandas
        gdf_segs = gpd.GeoDataFrame( dfsegs, geometry=stream_lines, crs="EPSG:4326")


        # Save to GeoPackage
        gdf_segs.to_file(self._file_output, driver="GPKG")

        self.logger.info("LSDTT Network Tool Operation complete")


        """
        #############################################################################
        # If we subdivide the network further, we could make it better for plotting #
        #############################################################################
        subseg_target_length = 200.
        seg_length = segment['flow_distance'].max() - segment['flow_distance'].min()
        n_subseg = int(np.round(seg_length/subseg_target_length))
        l_subseg_target2 = seg_length / n_subseg
        # The last one might be a bit longer, but it's just for plotting.
        subsegs = []
        for i in range(n_subseg-1):
            _dist = segment['flow_distance'] - segment['flow_distance'].min()
            subsegs.append( segment[ (_dist >= (subseg_target_length*i))
                                    & (_dist < (subseg_target_length*(i+1))) ] )
        subsegs.append( segment[ _dist >= subseg_target_length*(i+1)] )
            segment['flow_distance'].max()
        """


        """
        #Generating the geopackage to begin path selection
        print('Now I will create a geopackage to select segments for a path.')
        #Creating df to be used to select segment for path
        dfsegsselect= pd.DataFrame ({'id':segment_ids, 'toseg':toseg})
        # Create a set of LineString objects to be used for selection
        stream_lines_select = []
        for segment in segments:
            stream_lines_select.append( LineString(
                                    segment.loc[:, ('longitude', 'latitude', 'elevation')].values ) )
        gdf_segsselect = gpd.GeoDataFrame( dfsegsselect, geometry=stream_lines_select )
        # Save to GeoPackage
        # Not really necessary now that we have the full output
        gdf_segsselect.to_file('segs_select.gpkg', driver="GPKG")
        print('Your geopackage is ready!')
        print('Open in GIS to select your starter segment_ID.')
        """

        outputs = {"network": self._file_output}
        if self._export_all_nodes:
            self.logger.info("Exporting all nodes; this may take some time...")
            # Export nodes for use of plotting
            dfnodes = pd.concat(segments)
            dfnodes['network_node_type'] = ""
            #for mouth in mouth_nodes:
            #   dfnodes.loc[mouth]['network_node_type'] = 'mouth'
            gdf_NetworkNodes = gpd.GeoDataFrame( dfnodes, geometry=gpd.points_from_xy(dfnodes.longitude, dfnodes.latitude, dfnodes.elevation), crs="EPSG:4326")
            gdf_NetworkNodes.to_file(file_output_nodes, driver="GPKG")
            outputs["nodes"] = file_output_nodes
            self.logger.info('Nodes written to', file_output_nodes)

        self.qgis_dialog.progressBar.setValue(100)

        return outputs