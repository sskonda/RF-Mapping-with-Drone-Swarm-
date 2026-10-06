/* Select this main only for the continuous application; legacy mains are separate applications. */
#include "voxel_app.h"
#include "xparameters.h"
#include "xaxidma.h"
#include "xil_cache.h"
#include "xuartps.h"
#include "xuartps_hw.h"
#include "xtime_l.h"

enum { UART_BAUD = 115200, DMA_TIMEOUT_US = 1000000, PL_INITIALIZATION_US = 1000 };
static va_app application __attribute__((section(".voxel_ddr"), aligned(VM_CACHE_BYTES)));
static XAxiDma dma;
static XUartPs uart;
static uint64_t now_us(void)
{
    XTime ticks; XTime_GetTime(&ticks);
    /* Quotient/remainder preserve precision without overflowing ticks * 1000000. */
    return (uint64_t)(ticks / COUNTS_PER_SECOND) * UINT64_C(1000000) +
        (uint64_t)(ticks % COUNTS_PER_SECOND) * UINT64_C(1000000) / COUNTS_PER_SECOND;
}
static void flush(void *ctx, void *buffer, size_t length)
{
    (void)ctx; Xil_DCacheFlushRange((UINTPTR)buffer, (u32)length);
}
static void invalidate(void *ctx, void *buffer, size_t length)
{
    (void)ctx; Xil_DCacheInvalidateRange((UINTPTR)buffer, (u32)length);
}
static int start(void *buffer, size_t length, int direction)
{
    const UINTPTR channel = dma.RegBase + (direction == XAXIDMA_DEVICE_TO_DMA ? XAXIDMA_RX_OFFSET : XAXIDMA_TX_OFFSET);
    XAxiDma_WriteReg(channel, XAXIDMA_SR_OFFSET, XAXIDMA_IRQ_ALL_MASK);
    return XAxiDma_SimpleTransfer(&dma, (UINTPTR)buffer, (u32)length, direction) == XST_SUCCESS ? 0 : -1;
}
static int start_rx(void *ctx, void *buffer, size_t length)
{
    (void)ctx; return start(buffer, length, XAXIDMA_DEVICE_TO_DMA);
}
static int start_tx(void *ctx, const void *buffer, size_t length)
{
    (void)ctx; return start((void *)buffer, length, XAXIDMA_DMA_TO_DEVICE);
}
static int poll(void *ctx, size_t *length)
{
    (void)ctx;
    u32 tx = XAxiDma_ReadReg(dma.RegBase + XAXIDMA_TX_OFFSET, XAXIDMA_SR_OFFSET);
    u32 rx = XAxiDma_ReadReg(dma.RegBase + XAXIDMA_RX_OFFSET, XAXIDMA_SR_OFFSET);
    if ((tx | rx) & (XAXIDMA_ERR_ALL_MASK | XAXIDMA_IRQ_ERROR_MASK)) return -1;
    if ((tx & XAXIDMA_IRQ_IOC_MASK) && (rx & XAXIDMA_IRQ_IOC_MASK) &&
        (tx & XAXIDMA_IDLE_MASK) && (rx & XAXIDMA_IDLE_MASK)) {
        *length = XAxiDma_ReadReg(dma.RegBase + XAXIDMA_RX_OFFSET, XAXIDMA_BUFFLEN_OFFSET); return 1;
    }
    return 0;
}
static void halt(void *ctx)
{
    (void)ctx;
    /* Stop DMA asynchronously. This does not clear the PL map or restore synchronization. */
    XAxiDma_Reset(&dma);
}
static void result(void *ctx, const vm_request *q, const vm_result *r, const vm_slot *s)
{
    va_result(ctx, q, r, s);
}
static int initialize(void)
{
#ifndef SDT
    XAxiDma_Config *dc = XAxiDma_LookupConfig(XPAR_AXIDMA_0_DEVICE_ID);
    XUartPs_Config *uc = XUartPs_LookupConfig(XPAR_XUARTPS_0_DEVICE_ID);
#else
    XAxiDma_Config *dc = XAxiDma_LookupConfig(XPAR_XAXIDMA_0_BASEADDR);
    XUartPs_Config *uc = XUartPs_LookupConfig(XPAR_XUARTPS_0_BASEADDR);
#endif
    if (!dc || !uc || dc->HasSg || dc->HasMm2SDRE || dc->HasS2MmDRE ||
        !dc->HasMm2S || !dc->HasS2Mm) return -1;
    /* The only enabled PS UART is UART1; verify the generated BSP selection. */
#ifndef SDT
    if (uc->BaseAddress != XPAR_PS7_UART_1_BASEADDR) return -1;
#endif
    if (XAxiDma_CfgInitialize(&dma, dc) != XST_SUCCESS ||
        XUartPs_CfgInitialize(&uart, uc, uc->BaseAddress) != XST_SUCCESS ||
        XUartPs_SetBaudRate(&uart, UART_BAUD) != XST_SUCCESS) return -1;
    XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DMA_TO_DEVICE);
    XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DEVICE_TO_DMA);
    XUartPs_SetOperMode(&uart, XUARTPS_OPER_MODE_NORMAL);
    return 0;
}
int main(void)
{
    va_init(&application, DMA_TIMEOUT_US);
    if (initialize() != 0) return 1;
    const vm_io io = {&application, flush, invalidate, start_rx, start_tx, poll, halt, result};
    const uint64_t initialized_us = now_us();
    for (;;) {
        uint64_t time = now_us();
        /* No exported init_done register: initial backpressure plus this margin.
           START attests that FPGA and application were restarted together. */
        if (time - initialized_us < PL_INITIALIZATION_US) continue;
        u32 uart_errors = XUartPs_ReadReg(uart.Config.BaseAddress, XUARTPS_ISR_OFFSET) &
            (XUARTPS_IXR_OVER | XUARTPS_IXR_FRAMING | XUARTPS_IXR_PARITY);
        if (uart_errors) {
            ++application.protocol_errors;
            application.parser.discard = true;
            XUartPs_WriteReg(uart.Config.BaseAddress, XUARTPS_ISR_OFFSET, uart_errors);
        }
        for (unsigned i = 0; i < VA_UART_BUDGET && XUartPs_IsReceiveData(uart.Config.BaseAddress); ++i)
            va_input(&application, (uint8_t)XUartPs_ReadReg(uart.Config.BaseAddress, XUARTPS_FIFO_OFFSET));
        vm_service(&application.engine, &io, time);
        va_background(&application);
        for (unsigned i = 0; i < VA_UART_BUDGET && !XUartPs_IsTransmitFull(uart.Config.BaseAddress); ++i) {
            uint8_t byte;
            if (!va_output(&application, &byte)) break;
            XUartPs_WriteReg(uart.Config.BaseAddress, XUARTPS_FIFO_OFFSET, byte);
        }
    }
}
