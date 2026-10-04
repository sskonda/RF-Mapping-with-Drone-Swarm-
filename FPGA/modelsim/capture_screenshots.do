# Actual ModelSim Wave-window screenshots, using ImageMagick on Linux/X11.
# Run from FPGA/modelsim: vsim -gui -do capture_screenshots.do
# The regression must have completed successfully before capture.
do wave_views.do
set rf_captures {
    {axis_passthrough main 01_axis_passthrough_increment_wraparound_backpressure.png}
    {rf_packet_unpacker main 02_rf_packet_unpacker_signed_fields_prefetch_backpressure.png}
    {voxel main 03_voxel_signed_floor_four_stage_pipeline_stall.png}
    {voxel_lookup main 04_voxel_lookup_allocate_hit_full_rejection.png}
    {voxel_accumulator main 05_voxel_accumulator_signed_sum_count.png}
    {voxel_lookup collisions 06_voxel_lookup_collisions_linear_probing.png}
    {voxel_accumulator overflow 07_voxel_accumulator_count_saturation_overflow.png}
    {voxel_accumulator stall 08_voxel_accumulator_backpressure_no_duplicate_update.png}
}
set rf_capture_dir [file normalize [file join $rf_wave_dir ../waveform_screenshots]]
file mkdir $rf_capture_dir

proc rf_capture_next {} {
    global rf_captures
    if {[llength $rf_captures] == 0} {
        puts "Saved all 8 ModelSim Wave-window screenshots."
        return
    }
    lassign [lindex $rf_captures 0] module detail filename
    rf_show $module $detail
    # Let Tk and the window manager finish painting before taking the screenshot.
    after 1000 [list rf_capture_save $filename]
}

proc rf_capture_save {filename} {
    global rf_captures rf_capture_dir
    set tree [exec xwininfo -root -tree]
    if {![regexp {\n\s*(0x[0-9a-f]+) "[^\n]*": \("wave" "WindowObj"\)} $tree match window_id]} {
        error "Could not find the undocked ModelSim Wave window"
    }
    exec import -window $window_id [file join $rf_capture_dir $filename]
    puts "Saved $filename"
    set rf_captures [lrange $rf_captures 1 end]
    after 100 rf_capture_next
}

rf_capture_next
