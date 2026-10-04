/*
Author: Sanat Konda
Updated: Oct 4, 2026

Purpose: Send RF observations and verify accumulator results returned by AXI DMA.
Transmit four words, receive five words, and compare against a software model.
*/

#include "xparameters.h"
#include "xaxidma.h"
#include "xil_cache.h"
#include "xil_printf.h"
#include "xstatus.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#define TX_WORDS             4U
#define RX_WORDS             5U
#define TX_BYTES             (TX_WORDS * sizeof(u32))
#define RX_BYTES             (RX_WORDS * sizeof(u32))
#define BUFFER_ALIGNMENT     64U
#define DMA_TIMEOUT_COUNT    10000000U

#ifndef SDT
#define DMA_DEVICE_ID        XPAR_AXIDMA_0_DEVICE_ID
#else
#define DMA_BASE_ADDR        XPAR_XAXIDMA_0_BASEADDR
#endif

static XAxiDma dma;
/* Whole aligned cache lines keep DMA buffers separate from other variables. */
static u32 tx_buffer[BUFFER_ALIGNMENT / sizeof(u32)]
    __attribute__((aligned(BUFFER_ALIGNMENT)));
static u32 rx_buffer[BUFFER_ALIGNMENT / sizeof(u32)]
    __attribute__((aligned(BUFFER_ALIGNMENT)));

static const s32 packets[3][TX_WORDS] = {
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
    if (config == NULL || XAxiDma_CfgInitialize(&dma, config) != XST_SUCCESS) {
        xil_printf("ERROR: DMA configuration/initialization failed\r\n");
        return XST_FAILURE;
    }
    if (XAxiDma_HasSg(&dma)) {
        xil_printf("ERROR: use simple DMA mode\r\n");
        return XST_FAILURE;
    }
    XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DMA_TO_DEVICE);
    XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DEVICE_TO_DMA);
    return XST_SUCCESS;
}

static int transfer(const s32 *packet)
{
    u32 tx_status = 0U, rx_status = 0U;
    for (u32 i = 0U; i < TX_WORDS; ++i)
        tx_buffer[i] = (u32)packet[i];
    memset(rx_buffer, 0, sizeof(rx_buffer));
    Xil_DCacheFlushRange((UINTPTR)tx_buffer, sizeof(tx_buffer));
    Xil_DCacheFlushRange((UINTPTR)rx_buffer, sizeof(rx_buffer));

    /* Arm receive first. The returned packet is 20 bytes, not the 16-byte input. */
    if (XAxiDma_SimpleTransfer(&dma, (UINTPTR)rx_buffer, RX_BYTES,
                             XAXIDMA_DEVICE_TO_DMA) != XST_SUCCESS) {
        xil_printf("ERROR: S2MM did not start\r\n");
        return XST_FAILURE;
    }
    if (XAxiDma_SimpleTransfer(&dma, (UINTPTR)tx_buffer, TX_BYTES,
                             XAXIDMA_DMA_TO_DEVICE) != XST_SUCCESS) {
        xil_printf("ERROR: MM2S did not start\r\n");
        return XST_FAILURE;
    }

    for (u32 timeout = DMA_TIMEOUT_COUNT; timeout > 0U; --timeout) {
        tx_status = XAxiDma_ReadReg(dma.RegBase + XAXIDMA_TX_OFFSET, XAXIDMA_SR_OFFSET);
        rx_status = XAxiDma_ReadReg(dma.RegBase + XAXIDMA_RX_OFFSET, XAXIDMA_SR_OFFSET);
        if (((tx_status | rx_status) & XAXIDMA_ERR_ALL_MASK) != 0U) {
            xil_printf("ERROR: DMA TX status=0x%08x RX status=0x%08x\r\n",
                       (unsigned int)tx_status, (unsigned int)rx_status);
            return XST_FAILURE;
        }
        if (!XAxiDma_Busy(&dma, XAXIDMA_DMA_TO_DEVICE) &&
            !XAxiDma_Busy(&dma, XAXIDMA_DEVICE_TO_DMA)) {
            const u32 received_bytes = XAxiDma_ReadReg(
                dma.RegBase + XAXIDMA_RX_OFFSET, XAXIDMA_BUFFLEN_OFFSET);
            if (received_bytes != RX_BYTES) {
                xil_printf("ERROR: expected 20 receive bytes, got %d\r\n",
                           (int)received_bytes);
                return XST_FAILURE;
            }
            Xil_DCacheInvalidateRange((UINTPTR)rx_buffer, sizeof(rx_buffer));
            return XST_SUCCESS;
        }
    }
    xil_printf("ERROR: DMA timeout TX=0x%08x RX=0x%08x\r\n",
               (unsigned int)tx_status, (unsigned int)rx_status);
    return XST_FAILURE;
}

int main(void)
{
    int64_t sums[2] = {0, 0};
    uint32_t counts[2] = {0U, 0U}, slots[2] = {0U, 0U}, next_slot = 0U;
    xil_printf("\r\nVoxel DMA readout test: begin with a freshly reset FPGA map.\r\n");
    if (dma_init() != XST_SUCCESS)
        return XST_FAILURE;

    for (;;) {
        char command;
        xil_printf("Optional: arm ILA. Type 1 (A,-63), 2 (A,-67), 3 (B,-70), q (quit).\r\n");
        do {
            command = inbyte();
        } while ((command < '1' || command > '3') && command != 'q');
        if (command == 'q')
            return XST_SUCCESS;

        const unsigned int selection = (unsigned int)(command - '1');
        const unsigned int voxel_id = (selection == 2U) ? 1U : 0U;
        const uint32_t expected_new = (counts[voxel_id] == 0U) ? 1U : 0U;
        const uint32_t expected_slot = expected_new ? next_slot : slots[voxel_id];
        const uint32_t expected_count = counts[voxel_id] + 1U;
        const int64_t expected_sum = sums[voxel_id] + packets[selection][3];
        if (transfer(packets[selection]) != XST_SUCCESS)
            return XST_FAILURE;

        const uint32_t slot = rx_buffer[0], count = rx_buffer[3], flags = rx_buffer[4];
        const uint64_t sum_bits = ((uint64_t)rx_buffer[2] << 32) | rx_buffer[1];
        int64_t sum;
        memcpy(&sum, &sum_bits, sizeof(sum));
        printf("slot=%" PRIu32 " sum=%" PRId64 " count=%" PRIu32
               " new=%" PRIu32 " rejected=%" PRIu32 " overflow=%" PRIu32 "\r\n",
               slot, sum, count, flags & 1U, (flags >> 1) & 1U, (flags >> 2) & 1U);

        if (slot != expected_slot || sum != expected_sum ||
            count != expected_count || flags != expected_new) {
            printf("FAIL: expected slot=%" PRIu32 " sum=%" PRId64
                   " count=%" PRIu32 " flags=%" PRIu32 "\r\n",
                   expected_slot, expected_sum, expected_count, expected_new);
            return XST_FAILURE;
        }
        slots[voxel_id] = slot;
        sums[voxel_id] = sum;
        counts[voxel_id] = count;
        next_slot += expected_new;
        xil_printf("PASS: FPGA accumulator result matches the software model\r\n");
    }
}
