/*
Author: Sanat Konda
Updated: Sept 25, 2026

Purpose: Send repeatable RF observations after the ILA is armed.
UART keys 1, 2, and 3 select test packets; DMA verifies unchanged loopback data.
*/

#include "xparameters.h"
#include "xaxidma.h"
#include "xil_cache.h"
#include "xil_printf.h"
#include "xstatus.h"

#define BUFFER_WORDS        4U
#define BUFFER_BYTES        (BUFFER_WORDS * sizeof(u32))
#define DMA_TIMEOUT_COUNT   10000000U
#define BUFFER_ALIGNMENT    64U

#ifndef SDT
#define DMA_DEVICE_ID       XPAR_AXIDMA_0_DEVICE_ID
#else
#define DMA_BASE_ADDR       XPAR_XAXIDMA_0_BASEADDR
#endif

static XAxiDma dma;
static u32 tx_buffer[BUFFER_WORDS] __attribute__((aligned(BUFFER_ALIGNMENT)));
static u32 rx_buffer[BUFFER_WORDS] __attribute__((aligned(BUFFER_ALIGNMENT)));

/* x_mm, y_mm, z_mm, rssi_dbm: keys 1 and 2 address the same voxel. */
static const s32 test_packets[3][BUFFER_WORDS] = {
    {1250, 500, 1750, -63},
    {1250, 500, 1750, -67},
    {1750, 500, 1750, -70}
};

static int dma_init(void)
{
    XAxiDma_Config *config;
#ifndef SDT
    config = XAxiDma_LookupConfig(DMA_DEVICE_ID);
#else
    config = XAxiDma_LookupConfig(DMA_BASE_ADDR);
#endif
    if (config == NULL) {
        xil_printf("ERROR: DMA configuration not found\r\n");
        return XST_FAILURE;
    }
    if (XAxiDma_CfgInitialize(&dma, config) != XST_SUCCESS) {
        xil_printf("ERROR: DMA initialization failed\r\n");
        return XST_FAILURE;
    }
    if (XAxiDma_HasSg(&dma)) {
        xil_printf("ERROR: DMA is configured for scatter-gather mode\r\n");
        return XST_FAILURE;
    }
    XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DMA_TO_DEVICE);
    XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DEVICE_TO_DMA);
    return XST_SUCCESS;
}

static void initialize_buffers(const s32 *packet)
{
    for (u32 i = 0U; i < BUFFER_WORDS; ++i) {
        tx_buffer[i] = (u32)packet[i];
        rx_buffer[i] = 0U;
    }
    Xil_DCacheFlushRange((UINTPTR)tx_buffer, BUFFER_BYTES);
    Xil_DCacheFlushRange((UINTPTR)rx_buffer, BUFFER_BYTES);
}

static int run_dma_transfer(void)
{
    int status;
    u32 timeout = DMA_TIMEOUT_COUNT;

    status = XAxiDma_SimpleTransfer(&dma, (UINTPTR)rx_buffer,
                                  BUFFER_BYTES, XAXIDMA_DEVICE_TO_DMA);
    if (status != XST_SUCCESS) {
        xil_printf("ERROR: S2MM transfer failed to start\r\n");
        return XST_FAILURE;
    }
    status = XAxiDma_SimpleTransfer(&dma, (UINTPTR)tx_buffer,
                                  BUFFER_BYTES, XAXIDMA_DMA_TO_DEVICE);
    if (status != XST_SUCCESS) {
        xil_printf("ERROR: MM2S transfer failed to start\r\n");
        return XST_FAILURE;
    }
    while (timeout > 0U) {
        const int tx_busy = XAxiDma_Busy(&dma, XAXIDMA_DMA_TO_DEVICE);
        const int rx_busy = XAxiDma_Busy(&dma, XAXIDMA_DEVICE_TO_DMA);
        if (!tx_busy && !rx_busy)
            break;
        --timeout;
    }
    if (timeout == 0U) {
        xil_printf("ERROR: DMA transfer timed out\r\n");
        return XST_FAILURE;
    }
    Xil_DCacheInvalidateRange((UINTPTR)rx_buffer, BUFFER_BYTES);
    return XST_SUCCESS;
}

static int verify_data(void)
{
    for (u32 i = 0U; i < BUFFER_WORDS; ++i) {
        if (rx_buffer[i] != tx_buffer[i]) {
            xil_printf("ERROR: word %d expected 0x%08x received 0x%08x\r\n",
                       (int)i, (unsigned int)tx_buffer[i], (unsigned int)rx_buffer[i]);
            return XST_FAILURE;
        }
    }
    return XST_SUCCESS;
}

int main(void)
{
    xil_printf("\r\nVoxel accumulator ILA test\r\n");
    if (dma_init() != XST_SUCCESS)
        return XST_FAILURE;

    for (;;) {
        char command;
        xil_printf("Arm ILA, then type 1 (A,-63), 2 (A,-67), or 3 (B,-70).\r\n");
        do {
            command = inbyte();
        } while (command < '1' || command > '3');

        const s32 *packet = test_packets[command - '1'];
        initialize_buffers(packet);
        xil_printf("Sending x=%d y=%d z=%d RSSI=%d\r\n",
                   (int)packet[0], (int)packet[1], (int)packet[2], (int)packet[3]);
        if (run_dma_transfer() != XST_SUCCESS || verify_data() != XST_SUCCESS)
            return XST_FAILURE;
        xil_printf("PASS: DMA loopback. Check accumulator results in the ILA.\r\n");
    }
}
