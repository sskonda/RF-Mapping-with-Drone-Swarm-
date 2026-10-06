/* Compile the real BSP adapter against a register/cache/driver mock, not a replacement adapter. */
#define main firmware_main
#include "zybo_main.c"
#undef main
#include <assert.h>
#include <stdio.h>
static XAxiDma_Config config = {0,0,0,1,1};
static XUartPs_Config uart_config = {XPAR_XUARTPS_0_BASEADDR};
static u32 status_tx, status_rx, received_length;
static unsigned order;
static XTime fake_time;
XAxiDma_Config *XAxiDma_LookupConfig(UINTPTR address) { (void)address; return &config; }
XUartPs_Config *XUartPs_LookupConfig(UINTPTR address) { (void)address; return &uart_config; }
int XAxiDma_CfgInitialize(XAxiDma *d, XAxiDma_Config *c) { (void)c; d->RegBase=XPAR_XAXIDMA_0_BASEADDR; return 0; }
int XUartPs_CfgInitialize(XUartPs *u, XUartPs_Config *c, UINTPTR b) { assert(b==c->BaseAddress); u->Config=*c; return 0; }
int XUartPs_SetBaudRate(XUartPs *u, u32 baud) { (void)u; assert(baud==115200); return 0; }
void XUartPs_SetOperMode(XUartPs *u, u32 mode) { (void)u; assert(mode==0); }
void XAxiDma_IntrDisable(XAxiDma *d,u32 mask,int direction) { (void)d;(void)direction;assert(mask==XAXIDMA_IRQ_ALL_MASK); }
void XAxiDma_Reset(XAxiDma *d) { (void)d; }
u32 XAxiDma_ReadReg(UINTPTR address, u32 offset)
{
    if(offset==XAXIDMA_BUFFLEN_OFFSET) { assert(address==dma.RegBase+XAXIDMA_RX_OFFSET); return received_length; }
    assert(offset==XAXIDMA_SR_OFFSET);
    return address==dma.RegBase+XAXIDMA_RX_OFFSET ? status_rx : status_tx;
}
void XAxiDma_WriteReg(UINTPTR address,u32 offset,u32 value)
{
    assert(offset==XAXIDMA_SR_OFFSET && value==XAXIDMA_IRQ_ALL_MASK);
    if(address==dma.RegBase+XAXIDMA_RX_OFFSET) { assert(order==2); status_rx &= ~value; order=3; }
    else { assert(order==4); status_tx &= ~value; order=5; }
}
u32 XAxiDma_SimpleTransfer(XAxiDma *d, UINTPTR address,u32 length,int direction)
{
    (void)d;assert(address%64==0);
    if(direction==XAXIDMA_DEVICE_TO_DMA) { assert(order==3 && length==32);order=4; }
    else { assert(order==5 && length==28);order=6; }
    return 0;
}
void Xil_DCacheFlushRange(UINTPTR address,u32 length) { assert(address%64==0 && length==64 && order<2);order++; }
void Xil_DCacheInvalidateRange(UINTPTR address,u32 length) { assert(address%64==0 && length==64 && order==6);order=7; }
void XTime_GetTime(XTime *ticks) { *ticks=fake_time; }
int XUartPs_IsReceiveData(UINTPTR b) { (void)b;return 0; }
int XUartPs_IsTransmitFull(UINTPTR b) { (void)b;return 1; }
u32 XUartPs_ReadReg(UINTPTR b,u32 o) { (void)b;(void)o;return 0; }
void XUartPs_WriteReg(UINTPTR b,u32 o,u32 v) { (void)b;(void)o;(void)v; }
int main(void)
{
    assert(initialize()==0);config.HasSg=1;assert(initialize()==-1);config.HasSg=0;
    va_init(&application,1000);
    status_tx=status_rx=XAXIDMA_IRQ_IOC_MASK;
    flush(NULL,application.engine.tx,64);flush(NULL,application.engine.rx,64);
    assert(start_rx(NULL,application.engine.rx,32)==0 && start_tx(NULL,application.engine.tx,28)==0);
    size_t length=0;assert(poll(NULL,&length)==0);
    status_tx=XAXIDMA_IRQ_IOC_MASK|XAXIDMA_IDLE_MASK;assert(poll(NULL,&length)==0);
    status_rx=XAXIDMA_IRQ_IOC_MASK|XAXIDMA_IDLE_MASK;received_length=32;
    assert(poll(NULL,&length)==1 && length==32);
    invalidate(NULL,application.engine.rx,64);assert(order==7);
    status_rx|=XAXIDMA_IRQ_ERROR_MASK;assert(poll(NULL,&length)==-1);
    fake_time=COUNTS_PER_SECOND*UINT64_C(123456789)+COUNTS_PER_SECOND/2;
    assert(now_us()==UINT64_C(123456789499999));
    puts("PASS actual BSP adapter with mocked vendor calls (not vendor compilation)");
    return 0;
}
