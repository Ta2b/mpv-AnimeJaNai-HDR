/* Optional Submit/Complete extension of surface.h. Definitions are independent
 * of native storage/fence APIs; only capabilities actually queried may be used.
 * Synchronous Surfacev1 and ABI1/ABI9 remain separate available interfaces. */
#pragma once
#include "surface.h"
#ifdef __cplusplus
extern "C" {
#endif
enum aji_surface_async_status { AJI_SURFACE_ASYNC_BUSY=-4, AJI_SURFACE_ASYNC_CANCELLED=-5 };
enum aji_surface_completion_state { AJI_SURFACE_PENDING=1, AJI_SURFACE_FINISHED=2,
    AJI_SURFACE_FAILED=3, AJI_SURFACE_CANCELLED=4 };
enum aji_surface_dependency_kind { AJI_SURFACE_DEP_NONE=0, AJI_SURFACE_DEP_CUDA_EVENT=1,
    AJI_SURFACE_DEP_HIP_EVENT=2, AJI_SURFACE_DEP_D3D12_FENCE=3,
    AJI_SURFACE_DEP_METAL_EVENT=4, AJI_SURFACE_DEP_VULKAN_TIMELINE=5 };
enum aji_surface_submit_flags { AJI_SURFACE_BORROW_UNTIL_COMPLETE=1 };
enum aji_surface_complete_flags { AJI_SURFACE_CONSUME_RESULT=1 };
enum aji_surface_drain_flags { AJI_SURFACE_CANCEL_QUEUED=1, AJI_SURFACE_DROP_RESULTS=2 };
typedef struct aji_surface_dependency_v1 {
    uint32_t kind,reserved;
    void *event;
    uint64_t value;
} aji_surface_dependency_v1;
typedef struct aji_surface_submit_v1_request {
    uint32_t struct_size,version,flags,dependency_count;
    const aji_surface_v1 *previous,*current,*output;
    double timestep;
    void *execution_queue;
    aji_surface_dependency_v1 dependencies[3];
} aji_surface_submit_v1_request;
typedef struct aji_surface_completion_v1 {
    uint32_t struct_size,version,state,reserved;
    uint64_t ticket;
    int32_t status;
    uint32_t reserved_status;
    char message[256];
} aji_surface_completion_v1;
typedef struct aji_surface_async_caps_v1 {
    uint32_t struct_size,version,max_capacity,owner_callbacks_required;
    uint64_t dependency_mask;
    uint32_t device_kind,reserved;
} aji_surface_async_caps_v1;

typedef struct aji_surface_fence_v1_result {
    uint32_t struct_size,version,kind,reserved;
    void *event;
    uint64_t value;
} aji_surface_fence_v1_result;

/* Optional native output fence. BUSY until the worker has recorded it, then
 * OK may precede pixel completion. This borrowed event remains valid only until
 * ticket consumption or result drop/disable. Enqueue the consumer GPU wait
 * before retiring the ticket. Keep separate consumer references to its buffers.
 * Failed/cancelled tickets have no usable output. The input event handles and
 * queue handles supplied to Submit must remain alive until terminal completion;
 * input events must already have been recorded before Submit (completion may
 * still be pending). An unrecorded CUDA event does not create a dependency.
 * owners must also retain dependencies when needed. Input writes already ordered
 * before these producer events may finish; afterwards inputs stay immutable until
 * terminal completion. GPU consumers may read outputs after the exported GPU
 * wait with their own references, even before CPU Complete becomes terminal.
 * No implicit native import.
 * CPU providers may omit this optional symbol entirely. */
int aji_surface_output_fence_v1(void *context,uint64_t ticket,aji_surface_fence_v1_result *,size_t);

/* Enable after successful configure. One queue exclusively owns the context
 * until disable; no concurrent legacy configure/process/hints. Lifecycle calls
 * are serial, Submit/Complete may run concurrently after enable. Context destroy
 * drains/cancels the queue before releasing the inference state.
 *
 * A successful submit copies descriptors and retains owners, reserving a ticket;
 * it does NOT promise completed pixels. Submit never waits for model execution
 * or free queue capacity. A full queue returns BUSY/ticket0 without acquisition.
 * Owner callbacks can run on submit/worker/drain threads and must be thread-safe;
 * they must not throw, fail, reenter, or wait for this queue. Without
 * paired callbacks, BORROW_UNTIL_COMPLETE is an explicit caller promise that all
 * buffers remain immutable/allocated until completion, including cancel/error.
 * CPU v1 only accepts already-ready host data, no external fence/execution_queue.
 *
 * Complete is a nonblocking poll: PENDING does not grant output access/reuse.
 * FINISHED/FAILED/CANCELLED are published only after all pixel work stops and
 * references are released. Discard outputs on FAILED/CANCELLED. CONSUME frees
 * the result slot only when completed, never a pending slot. Tickets are monotone
 * and never recycled within this context, including disable/re-enable.
 *
 * Drain explicitly waits for active work. CANCEL_QUEUED skips work not started;
 * running work finishes before references are released. DROP_RESULTS retires old
 * tickets for seek/reset; new tickets remain monotone. Disable cancels/drains and
 * drops results. After draining a seek, derived identities must also be reset.
 * Query/Complete short/null outputs are untouched; missing/retired tickets fail.
 */
/* Optional terminal-completion notification. Register/clear only while the
 * queue is disabled; enable/drain/disable remain serial lifecycle operations.
 * The callback runs after terminal state and owner releases are published, on
 * the worker or drain thread. It must be thread-safe, nonblocking and must not
 * reenter this context. It only wakes the client; Complete remains authoritative.
 * Keep its opaque alive until disable returns, then clear before client teardown.
 * Providers may omit this optional symbol. No callbacks occur after disable. */
typedef void (*aji_surface_wakeup_fn)(void *opaque);
int aji_surface_set_wakeup_v1(void *context,aji_surface_wakeup_fn callback,void *opaque);

int aji_surface_async_query_v1(void *context,uint32_t version,aji_surface_async_caps_v1 *,size_t);
int aji_surface_async_enable_v1(void *context,uint32_t capacity);
int aji_surface_submit_v1(void *context,const aji_surface_submit_v1_request *,uint64_t *ticket);
int aji_surface_complete_v1(void *context,uint64_t ticket,uint32_t flags,aji_surface_completion_v1 *,size_t);
int aji_surface_drain_v1(void *context,uint32_t flags);
int aji_surface_async_disable_v1(void *context);
#ifdef __cplusplus
}
#endif
