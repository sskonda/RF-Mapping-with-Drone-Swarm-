#ifndef VENDOR_MOCK_H
#define VENDOR_MOCK_H
#include <stddef.h>
#include <stdint.h>
typedef uint32_t u32;
typedef uintptr_t UINTPTR;
typedef uint64_t XTime;
enum { XPAR_AXIDMA_0_DEVICE_ID=0, XPAR_XUARTPS_0_DEVICE_ID=0,
       XPAR_XAXIDMA_0_BASEADDR=0x40400000, XST_SUCCESS=0,
       XAXIDMA_DMA_TO_DEVICE=0, XAXIDMA_DEVICE_TO_DMA=1,
       XAXIDMA_TX_OFFSET=0, XAXIDMA_RX_OFFSET=0x30, XAXIDMA_SR_OFFSET=4,
       XAXIDMA_BUFFLEN_OFFSET=0x28, XAXIDMA_IRQ_ALL_MASK=0x7000,
       XAXIDMA_IRQ_IOC_MASK=0x1000, XAXIDMA_IRQ_ERROR_MASK=0x4000,
       XAXIDMA_ERR_ALL_MASK=0x770, XAXIDMA_IDLE_MASK=2,
       XUARTPS_OPER_MODE_NORMAL=0, XUARTPS_FIFO_OFFSET=0x30, XUARTPS_ISR_OFFSET=0x14,
       XUARTPS_IXR_OVER=0x20, XUARTPS_IXR_FRAMING=0x40, XUARTPS_IXR_PARITY=0x80 };
#define XPAR_XUARTPS_0_BASEADDR UINT32_C(0xe0001000)
#define XPAR_PS7_UART_1_BASEADDR XPAR_XUARTPS_0_BASEADDR
#define COUNTS_PER_SECOND UINT64_C(333333333)
typedef struct { UINTPTR RegBase; } XAxiDma;
typedef struct { int HasSg, HasMm2SDRE, HasS2MmDRE, HasMm2S, HasS2Mm; } XAxiDma_Config;
typedef struct { UINTPTR BaseAddress; } XUartPs_Config;
typedef struct { XUartPs_Config Config; } XUartPs;
XAxiDma_Config *XAxiDma_LookupConfig(UINTPTR);
XUartPs_Config *XUartPs_LookupConfig(UINTPTR);
int XAxiDma_CfgInitialize(XAxiDma *, XAxiDma_Config *);
int XUartPs_CfgInitialize(XUartPs *, XUartPs_Config *, UINTPTR);
int XUartPs_SetBaudRate(XUartPs *, u32);
void XUartPs_SetOperMode(XUartPs *, u32);
void XAxiDma_IntrDisable(XAxiDma *, u32, int);
void XAxiDma_Reset(XAxiDma *);
u32 XAxiDma_ReadReg(UINTPTR, u32);
void XAxiDma_WriteReg(UINTPTR, u32, u32);
u32 XAxiDma_SimpleTransfer(XAxiDma *, UINTPTR, u32, int);
void Xil_DCacheFlushRange(UINTPTR, u32);
void Xil_DCacheInvalidateRange(UINTPTR, u32);
void XTime_GetTime(XTime *);
int XUartPs_IsReceiveData(UINTPTR);
int XUartPs_IsTransmitFull(UINTPTR);
u32 XUartPs_ReadReg(UINTPTR, u32);
void XUartPs_WriteReg(UINTPTR, u32, u32);
#endif
