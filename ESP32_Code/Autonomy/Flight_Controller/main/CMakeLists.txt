idf_component_register(SRCS "main.c" "sensors.c" "sensor_decode.c" "bench.c" "motors.c"
    INCLUDE_DIRS "."
    LDFRAGMENTS "motor_stop.lf"
    REQUIRES esp_driver_i2c esp_driver_uart esp_driver_mcpwm esp_driver_gptimer
             esp_driver_gpio esp_timer esp_system)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -Wdouble-promotion -fstack-usage)
