# In the ModelSim GUI: do wave_views.do; rf_show voxel
# These views read the WLF files produced by run_regression.py.
# ModelSim's do command does not set Tcl info script to the .do file's path.
# Open the project first (which changes cwd), or cd to FPGA/modelsim.
set rf_wave_dir [pwd]

proc rf_signal {scope signal {radix unsigned} {color {#7ee787}}} {
    global rf_dataset
    add wave -noupdate -height 25 -radix $radix -color $color \
        -label [file tail $signal] $rf_dataset:/$scope/$signal
}

proc rf_show {module {detail main}} {
    global rf_wave_dir rf_dataset rf_loaded
    array set tops {
        axis_passthrough axis_passthrough_tb
        rf_packet_unpacker rf_packet_unpacker_tb
        voxel voxel_tb
        voxel_lookup tb_voxel_lookup
        voxel_accumulator tb_voxel_accumulator
    }
    if {![info exists tops($module)]} {error "Unknown RTL module: $module"}
    view wave -undock -width 1840 -height 900 -x 20 -y 40
    delete wave *
    # Keep each dataset open. Closing the active context can crash ModelSim 2020.1.
    set rf_dataset rf_$module
    if {![info exists rf_loaded($module)]} {
        dataset open [file join $rf_wave_dir waves $tops($module).wlf] $rf_dataset
        set rf_loaded($module) 1
    }
    # Explicit pixel sizes also work on legacy ModelSim installations with bad DPI scaling.
    foreach name {waveFont waveFontBold waveFontUnderline waveFontBoldUnderline} {
        font configure $name -family {DejaVu Sans Mono} -size -16
    }
    add wave -noupdate -divider "$module.sv | ModelSim simulation"
    switch -- $module {
        axis_passthrough {
            set scope axis_passthrough_tb/default_words
            set start 20ns; set end 205ns; set cursor 85ns
            add wave -noupdate -divider {32-bit words: output = input + 1}
            foreach s {aclk aresetn} {rf_signal $scope $s binary}
            foreach s {s_axis_tdata s_axis_tvalid s_axis_tready s_axis_tlast} {
                rf_signal $scope $s
            }
            add wave -noupdate -divider {Hold 42 while stalled; max + 1 wraps to 0}
            foreach s {m_axis_tdata m_axis_tvalid m_axis_tready m_axis_tlast} {
                rf_signal $scope $s unsigned {#79c0ff}
            }
        }
        rf_packet_unpacker {
            set scope rf_packet_unpacker_tb
            set start 20ns; set end 190ns; set cursor 115ns
            add wave -noupdate -divider {X/Y/Z prefetch; fourth word waits for ready}
            foreach s {aclk aresetn} {rf_signal $scope $s binary}
            foreach s {s_axis_tdata m_axis_tdata} {rf_signal $scope $s decimal}
            foreach s {s_axis_tvalid s_axis_tready s_axis_tlast m_axis_tvalid m_axis_tready m_axis_tlast} {
                rf_signal $scope $s binary
            }
            add wave -noupdate -divider {Complete signed tuple stays stable during stall}
            foreach s {x_mm y_mm z_mm rssi_dbm} {
                rf_signal $scope $s decimal {#79c0ff}
            }
            foreach s {observation_valid observation_ready} {
                rf_signal $scope $s binary {#79c0ff}
            }
        }
        voxel {
            set scope voxel_tb/default_grid
            set start 20ns; set end 200ns; set cursor 105ns
            add wave -noupdate -divider {500 mm grid | floor division | four stages}
            foreach s {aclk aresetn} {rf_signal $scope $s binary}
            foreach s {x_mm y_mm z_mm rssi_dbm} {rf_signal $scope $s decimal}
            foreach s {observation_valid observation_ready} {rf_signal $scope $s binary}
            rf_signal $scope dut/voxel_inst/stage_valid binary {#ffa657}
            add wave -noupdate -divider {(-1,-500,-501) mm maps to (-1,-1,-2)}
            foreach s {vx vy vz voxel_rssi_dbm} {rf_signal $scope $s decimal {#79c0ff}}
            foreach s {voxel_valid voxel_ready} {rf_signal $scope $s binary {#79c0ff}}
        }
        voxel_lookup {
            set scope tb_voxel_lookup/non_power_two
            set start 110ns; set end 390ns; set cursor 170ns
            add wave -noupdate -divider {5 slots / 8 buckets | new, repeated and full}
            foreach s {aclk aresetn init_done} {rf_signal $scope $s binary}
            foreach s {voxel_x voxel_y voxel_z voxel_rssi_dbm} {rf_signal $scope $s decimal}
            foreach s {voxel_valid voxel_ready} {rf_signal $scope $s binary}
            if {$detail == "collisions"} {
                add wave -noupdate -divider {Collisions probe next bucket; slots persist}
            } else {
                add wave -noupdate -divider {Same key keeps slot 0; full-map new keys reject}
            }
            foreach s {lookup_slot lookup_new lookup_rejected lookup_valid lookup_ready used_voxels map_full} {
                rf_signal $scope $s unsigned {#79c0ff}
            }
            if {$detail == "collisions"} {
                set start 510ns; set end 940ns; set cursor 750ns
                rf_signal $scope dut/voxel_lookup_inst/address unsigned {#ffa657}
                rf_signal $scope dut/voxel_lookup_inst/attempts unsigned {#ffa657}
            }
        }
        voxel_accumulator {
            set scope tb_voxel_accumulator/small_map
            set start 40ns; set end 140ns; set cursor 90ns
            add wave -noupdate -divider {5 slots | 3-bit count | signed RSSI sum}
            foreach s {aclk aresetn} {rf_signal $scope $s binary}
            foreach s {lookup_slot lookup_new lookup_rejected lookup_valid lookup_ready} {
                rf_signal $scope $s
            }
            rf_signal $scope lookup_rssi_dbm decimal
            if {$detail == "overflow"} {
                add wave -noupdate -divider {Count 7 saturates; overflow rejects the update}
            } elseif {$detail == "stall"} {
                add wave -noupdate -divider {Hold sum/count during stall; consume only once}
            } else {
                add wave -noupdate -divider {New -63; next -67 gives sum -130, count 2}
            }
            foreach s {acc_slot acc_count acc_new acc_rejected acc_overflow acc_valid acc_ready} {
                rf_signal $scope $s unsigned {#79c0ff}
            }
            rf_signal $scope acc_rssi_sum decimal {#79c0ff}
            if {$detail == "overflow"} {
                set start 180ns; set end 350ns; set cursor 265ns
            } elseif {$detail == "stall"} {
                set start 450ns; set end 840ns; set cursor 650ns
            }
        }
    }
    set height 760
    if {$module == "axis_passthrough"} {set height 550}
    if {$detail == "collisions"} {set height 840}
    view wave -undock -width 1840 -height $height -x 20 -y 40
    configure wave -namecolwidth 500 -valuecolwidth 175 -timelineunits ns \
        -signalnamewidth 1 -justifyvalue left -gridperiod 10 -rowmargin 5
    update
    wave zoom range $start $end
    wave cursor configure 1 -name {Inspect behavior}
    wave cursor active 1
    wave cursor time -time $cursor 1
    view wave -title "$module.sv - $detail - ModelSim"
    update
}
