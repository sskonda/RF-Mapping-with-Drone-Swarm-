# Run from FPGA/modelsim: vsim -c -do create_project.do
# Paths in the generated project remain relative to this directory.
onerror {quit -f -code 1}
if {![file exists work]} {vlib work}
project new . rf_mapping work "$env(MODEL_TECH)/../modelsim.ini" 0
project addfolder RTL
project addfolder Testbenches
foreach source [lsort [glob ../rtl/*.sv ../rtl/*.v]] {
    project addfile $source {} RTL
}
foreach source [lsort [glob ../tb/*.sv]] {
    project addfile $source {} Testbenches
}
project close
# ModelSim expands addfile paths when saving; restore portable file references.
quietly set f [open rf_mapping.mpf r]
quietly set contents [read $f]
close $f
quietly set contents [string map [list "[file normalize ..]/" "../"] $contents]
quietly set f [open rf_mapping.mpf w]
puts -nonewline $f $contents
close $f
quit -f
