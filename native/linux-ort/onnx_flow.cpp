/* A RIFE 4.x model with its motion field and mask as extra outputs (see onnx_flow.h).
 *
 * The ONNX file is edited at the protobuf wire level, without an onnx dependency: the graph's
 * nodes are read to find the two tensors, then two ValueInfoProto entries are appended to the
 * graph's outputs. Every other byte, the weights included, is copied as it is.
 */
#include "onnx_flow.h"

#include <cstdint>
#include <map>

namespace {

struct Reader {
    const uint8_t *p, *end;
    bool ok = true;

    uint64_t varint()
    {
        uint64_t v = 0;
        for (int shift = 0; p < end && shift < 64; shift += 7) {
            const uint8_t b = *p++;
            v |= (uint64_t)(b & 0x7f) << shift;
            if (!(b & 0x80))
                return v;
        }
        ok = false;
        return 0;
    }

    // The next field: its number, and for a length-delimited one its bytes.
    bool next(uint32_t *field, const uint8_t **data, size_t *len)
    {
        *data = nullptr;
        *len = 0;
        if (!ok || p >= end)
            return false;
        const uint64_t tag = varint();
        *field = (uint32_t)(tag >> 3);
        switch (tag & 7) {
        case 0: varint(); break;
        case 1: if (end - p < 8) ok = false; else p += 8; break;
        case 5: if (end - p < 4) ok = false; else p += 4; break;
        case 2: {
            const uint64_t n = varint();
            if (!ok || (uint64_t)(end - p) < n) { ok = false; break; }
            *data = p;
            *len = (size_t)n;
            p += n;
            break;
        }
        default: ok = false;
        }
        return ok;
    }
};

struct Node {
    std::string op;
    std::vector<std::string> in, out;
};

void put_varint(std::string &s, uint64_t v)
{
    while (v >= 0x80) {
        s += (char)(v | 0x80);
        v >>= 7;
    }
    s += (char)v;
}

// GraphProto.output (field 12): ValueInfoProto{name, type{tensor_type{elem_type, shape}}}, the
// shape being four dimensions of unstated size.
std::string output_entry(const std::string &name, int elem_type)
{
    std::string tensor(1, (char)0x08);
    put_varint(tensor, (uint64_t)elem_type);
    tensor += (char)0x12;
    tensor += (char)8;
    for (int i = 0; i < 4; i++) {
        tensor += (char)0x0a;
        tensor += (char)0;
    }
    std::string type(1, (char)0x0a);
    put_varint(type, tensor.size());
    type += tensor;
    std::string info(1, (char)0x0a);
    put_varint(info, name.size());
    info += name;
    info += (char)0x12;
    put_varint(info, type.size());
    info += type;
    std::string field(1, (char)0x62);
    put_varint(field, info.size());
    return field + info;
}

} // namespace

bool aji_onnx_add_flow_outputs(const std::vector<char> &model, std::vector<char> *out,
                               std::string *why)
{
    const uint8_t *base = (const uint8_t *)model.data();
    Reader top{base, base + model.size()};
    const uint8_t *graph = nullptr, *graph_field = nullptr, *after = nullptr;
    size_t graph_len = 0;
    for (;;) {
        const uint8_t *start = top.p;
        uint32_t field;
        const uint8_t *data;
        size_t len;
        if (!top.next(&field, &data, &len))
            break;
        if (field == 7 && data) {
            graph = data;
            graph_len = len;
            graph_field = start;
            after = top.p;
        }
    }
    if (!top.ok || !graph) {
        *why = "not an ONNX model";
        return false;
    }

    std::vector<Node> nodes;
    int elem_type = 0;
    Reader g{graph, graph + graph_len};
    uint32_t field;
    const uint8_t *data;
    size_t len;
    while (g.next(&field, &data, &len)) {
        if (field == 1 && data) {
            Node n;
            Reader r{data, data + len};
            uint32_t f;
            const uint8_t *d;
            size_t l;
            while (r.next(&f, &d, &l)) {
                if (!d)
                    continue;
                if (f == 1) n.in.emplace_back((const char *)d, l);
                else if (f == 2) n.out.emplace_back((const char *)d, l);
                else if (f == 4) n.op.assign((const char *)d, l);
            }
            nodes.push_back(std::move(n));
        } else if (field == 12 && data && !elem_type) {
            // the picture's element type: ValueInfoProto.type(2).tensor_type(1).elem_type(1)
            Reader info{data, data + len};
            uint32_t f;
            const uint8_t *d;
            size_t l;
            while (info.next(&f, &d, &l)) {
                if (f != 2 || !d)
                    continue;
                Reader type{d, d + l};
                while (type.next(&f, &d, &l)) {
                    if (f != 1 || !d)
                        continue;
                    Reader tensor{d, d + l};
                    while (tensor.p < tensor.end && tensor.ok) {
                        const uint64_t tag = tensor.varint();
                        if ((tag >> 3) == 1 && (tag & 7) == 0) {
                            elem_type = (int)tensor.varint();
                            break;
                        }
                        break;
                    }
                }
            }
        }
    }
    if (!g.ok || nodes.empty() || !elem_type) {
        *why = "unreadable graph";
        return false;
    }

    std::map<std::string, const Node *> made;
    const Node *sample = nullptr, *sigmoid = nullptr;
    for (const Node &n : nodes) {
        for (const std::string &o : n.out)
            made[o] = &n;
        if (n.op == "GridSample") sample = &n;
        if (n.op == "Sigmoid") sigmoid = &n;
    }
    auto maker = [&](const std::string &name, const char *op) -> const Node * {
        auto it = made.find(name);
        return it != made.end() && it->second->op == op ? it->second : nullptr;
    };
    // grid of the last warp = Transpose(Add(mesh, Mul(Cast(Reshape(flow)), scale)))
    std::string flow;
    const Node *transpose = sample && sample->in.size() > 1 ? maker(sample->in[1], "Transpose") : nullptr;
    const Node *add = transpose && !transpose->in.empty() ? maker(transpose->in[0], "Add") : nullptr;
    if (add) {
        for (const std::string &a : add->in) {
            const Node *mul = maker(a, "Mul");
            if (!mul)
                continue;
            for (const std::string &m : mul->in) {
                const Node *cast = maker(m, "Cast");
                const Node *reshape = cast && !cast->in.empty() ? maker(cast->in[0], "Reshape") : nullptr;
                if (reshape && !reshape->in.empty())
                    flow = reshape->in[0];
            }
        }
    }
    if (flow.empty() || !sigmoid || sigmoid->out.empty()) {
        *why = "the motion field or the mask was not found (not a RIFE 4.x model as exported for the project)";
        return false;
    }

    const std::string extra = output_entry(flow, elem_type) + output_entry(sigmoid->out[0], elem_type);
    std::string head(1, (char)0x3a);   // ModelProto.graph: field 7, length-delimited
    put_varint(head, graph_len + extra.size());
    out->clear();
    out->reserve(model.size() + extra.size() + 16);
    out->insert(out->end(), model.data(), (const char *)graph_field);
    out->insert(out->end(), head.begin(), head.end());
    out->insert(out->end(), (const char *)graph, (const char *)graph + graph_len);
    out->insert(out->end(), extra.begin(), extra.end());
    out->insert(out->end(), (const char *)after, model.data() + model.size());
    return true;
}
