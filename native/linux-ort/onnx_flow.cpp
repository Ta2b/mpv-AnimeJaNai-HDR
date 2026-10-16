/* A RIFE 4.x model with its motion field and mask as extra outputs (see onnx_flow.h).
 *
 * The ONNX file is edited at the protobuf wire level, without an onnx dependency: the graph's
 * nodes are read to find the two tensors, then two ValueInfoProto entries are appended to the
 * graph's outputs. Every other byte, the weights included, is copied as it is.
 */
#include "onnx_flow.h"
#include "../common/content_identity.h"

#include <cstdint>
#include <map>
#include <set>

namespace {

struct Reader {
    const uint8_t *p, *end;
    bool ok = true;
    uint64_t scalar = 0;
    unsigned wire = 0;

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
        if (!tag) { ok = false; return false; }
        *field = (uint32_t)(tag >> 3);
        scalar = 0;
        wire = (unsigned)(tag & 7);
        switch (wire) {
        case 0: scalar = varint(); break;
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

static bool cpu_activations_impl(const std::vector<char> &model, std::vector<char> *out, size_t *count)
{
    *count=0;
    auto field = [](uint32_t number,const std::string &value) {
        std::string s;put_varint(s,((uint64_t)number<<3)|2);put_varint(s,value.size());return s+value;
    };
    const auto *base = (const uint8_t *)model.data();
    Reader top{base,base+model.size()};uint32_t f;const uint8_t *d;size_t l;
    const uint8_t *graph=nullptr,*start_graph=nullptr,*end_graph=nullptr;size_t graph_len=0;
    while (top.p<top.end) {
        const auto *start=top.p;if(!top.next(&f,&d,&l))return false;
        if(f==7 && d) {graph=d;graph_len=l;start_graph=start;end_graph=top.p;}
    }
    if(!graph)return false;
    Reader g{graph,graph+graph_len};std::string changed;
    while(g.p<g.end) {
        const auto *start=g.p;if(!g.next(&f,&d,&l))return false;
        if(f!=1 || !d) {changed.append((const char *)start,(size_t)(g.p-start));continue;}
        Reader node{d,d+l};uint32_t k;const uint8_t *v;size_t z;std::string op,input,output;
        while(node.next(&k,&v,&z))if(v) {
            if(k==4)op.assign((const char *)v,z);
            else if(k==1)input.assign((const char *)v,z);
            else if(k==2)output.assign((const char *)v,z);
        }
        if(!node.ok)return false;
        if(op!="LeakyRelu") {changed.append((const char *)start,(size_t)(g.p-start));continue;}
        const std::string prefix="__aji_cpu_leaky_"+std::to_string(*count);
        const std::string in=prefix+"_float_in",out_name=prefix+"_float_out";
        // Cast attributes: AttributeProto{name="to",i=TYPE,type=INT}.
        auto cast = [&](const std::string &from,const std::string &to,const std::string &name,int type) {
            std::string attribute=field(1,"to");put_varint(attribute,24);put_varint(attribute,type);
            put_varint(attribute,160);put_varint(attribute,2);
            return field(1,field(1,from)+field(2,to)+field(3,name)+field(4,"Cast")+field(5,attribute));
        };
        changed+=cast(input,in,prefix+"_cast_in",1);
        std::string native;node=Reader{d,d+l};bool domain=false;
        while(node.p<node.end) {
            const auto *part=node.p;if(!node.next(&k,&v,&z))return false;
            if(k==1)native+=field(1,in);
            else if(k==2)native+=field(2,out_name);
            else if(k==4)native+=field(4,"AjiLeakyReluF32");
            else if(k==7) {native+=field(7,"aji.cpu");domain=true;}
            else native.append((const char *)part,(size_t)(node.p-part));
        }
        if(!domain)native+=field(7,"aji.cpu");
        changed+=field(1,native);changed+=cast(out_name,output,prefix+"_cast_out",10);++*count;
    }
    if(*count!=53)return false;
    std::string result((const char *)base,(size_t)(start_graph-base));result+=field(7,changed);
    result.append((const char *)end_graph,(size_t)(top.end-end_graph));
    std::string opset=field(1,"aji.cpu");put_varint(opset,16);put_varint(opset,1);result+=field(8,opset);
    out->assign(result.begin(),result.end());return true;
}

static bool prune_cpu_motion_nodes(const std::vector<char> &model,std::vector<char> *out,std::string *why)
{
    // Only called after the complete known RIFE content check. These graphs
    // are flat, deterministic tensor graphs: no If/Loop/Scan or captured inputs.
    const auto *base=(const uint8_t *)model.data();Reader top{base,base+model.size()};
    uint32_t f;const uint8_t *d;size_t l;
    const uint8_t *graph=nullptr,*graph_start=nullptr,*graph_after=nullptr;size_t length=0;
    while(top.p<top.end) {
        const auto *start=top.p;if(!top.next(&f,&d,&l))return false;
        if(f==7 && d) {graph=d;length=l;graph_start=start;graph_after=top.p;}
    }
    if(!graph)return false;
    struct Dependency {std::vector<std::string> inputs,outputs;};
    std::vector<Dependency> nodes;std::vector<std::string> needed;
    Reader read{graph,graph+length};
    while(read.p<read.end) {
        if(!read.next(&f,&d,&l))return false;
        if(f==1 && d) {
            Dependency node;Reader r{d,d+l};uint32_t k;const uint8_t *v;size_t n;
            while(r.next(&k,&v,&n))if(v) {
                if(k==1 && n)node.inputs.emplace_back((const char *)v,n);
                else if(k==2 && n)node.outputs.emplace_back((const char *)v,n);
                else if(k==4) {
                    const std::string op((const char *)v,n);
                    if(op=="If" || op=="Loop" || op=="Scan") {*why="CPU motion pruning requires a flat graph";return false;}
                }
            }
            if(!r.ok)return false;nodes.push_back(std::move(node));
        } else if(f==12 && d) {
            Reader info{d,d+l};uint32_t k;const uint8_t *v;size_t n;
            while(info.next(&k,&v,&n))if(k==1 && v && n)needed.emplace_back((const char *)v,n);
            if(!info.ok)return false;
        }
    }
    if(needed.size()!=2)return false;
    std::map<std::string,size_t> producers;
    for(size_t i=0;i<nodes.size();++i)for(const auto &name:nodes[i].outputs)
        if(!producers.emplace(name,i).second)return false;
    std::vector<bool> keep(nodes.size(),false);
    while(!needed.empty()) {
        auto name=std::move(needed.back());needed.pop_back();
        const auto found=producers.find(name);
        if(found==producers.end() || keep[found->second])continue;
        const size_t i=found->second;keep[i]=true;
        needed.insert(needed.end(),nodes[i].inputs.begin(),nodes[i].inputs.end());
    }
    std::string body;size_t i=0;read=Reader{graph,graph+length};
    while(read.p<read.end) {
        const auto *start=read.p;if(!read.next(&f,&d,&l))return false;
        const bool retain=f!=1 || keep[i++];
        if(retain)body.append((const char *)start,(size_t)(read.p-start));
    }
    std::string result((const char *)base,(size_t)(graph_start-base));
    put_varint(result,58);put_varint(result,body.size());result+=body;
    result.append((const char *)graph_after,(size_t)(top.end-graph_after));
    out->assign(result.begin(),result.end());return true;
}

bool aji_onnx_prepare_cpu_rife(const std::vector<char> &model,bool activations,bool motion,
    std::vector<char> *out,size_t *count,bool *motion_only,std::string *why)
{
    *count=0;*motion_only=false;
    if(!activations && !motion)return false;
    aji::identity::Sha256 hash;hash.update(model.data(),model.size());
    const auto digest=hash.hex();
    if(digest!="fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59"
        && digest!="4d93a8a394cc1a1dd20d7efc2fcbace769f289dd655d0f76f941f533ffbbc216") {
        *why="CPU RIFE content is not qualified";return false;
    }
    std::vector<char> activated;
    const bool changed=activations && cpu_activations_impl(model,&activated,count);
    const auto &graph=changed ? activated : model;
    std::vector<char> moving;
    if(motion && aji_onnx_motion_outputs(graph,&moving,why) && prune_cpu_motion_nodes(moving,out,why)) {
        *motion_only=true;return true;
    }
    if(changed) { *out=std::move(activated);return true; }
    return false;
}

bool aji_onnx_cpu_activations(const std::vector<char> &model,std::vector<char> *out,size_t *count)
{
    bool motion_only=false;std::string why;
    return aji_onnx_prepare_cpu_rife(model,true,false,out,count,&motion_only,&why);
}

AjiFixedShape aji_onnx_fixed_rank4_input(const std::vector<char> &model,
    const std::array<int64_t, 4> &expected, std::vector<char> *out, std::string *why)
{
    struct Field { const uint8_t *start = nullptr, *data = nullptr, *after = nullptr; size_t len = 0; };
    // Locate a singular nested message, rejecting duplicate/malformed metadata.
    auto find = [](const uint8_t *p, size_t n, uint32_t wanted, Field *hit) {
        Reader r{p, p+n}; uint32_t f; const uint8_t *d; size_t l;
        while (r.p < r.end) {
            const uint8_t *start = r.p;
            if (!r.next(&f,&d,&l)) return false;
            if (f == wanted) {
                if (hit->start || !d) return false;
                *hit = {start,d,r.p,l};
            }
        }
        return r.ok && hit->start;
    };
    auto replace = [](const uint8_t *p, size_t n, const Field &f, uint32_t number, const std::string &body) {
        std::string s((const char *)p,(size_t)(f.start-p));
        put_varint(s,((uint64_t)number<<3)|2); put_varint(s,body.size()); s += body;
        s.append((const char *)f.after,(size_t)(p+n-f.after)); return s;
    };
    auto invalid = [&](const char *reason) { *why = reason; return AjiFixedShape::Invalid; };
    if (model.empty()) return invalid("Empty ONNX model");
    const auto *base = (const uint8_t *)model.data();
    Field graph, input, type, tensor, shape;
    if (!find(base,model.size(),7,&graph)) return invalid("Missing/ambiguous ONNX graph");
    if (!find(graph.data,graph.len,11,&input)) {
        *why = "requires a single graph input"; return AjiFixedShape::Unsupported;
    }
    if (!find(input.data,input.len,2,&type) || !find(type.data,type.len,1,&tensor)
        || !find(tensor.data,tensor.len,2,&shape)) {
        *why = "requires tensor input shape metadata"; return AjiFixedShape::Unsupported;
    }
    Reader rank_reader{shape.data,shape.data+shape.len}; uint32_t f; const uint8_t *d; size_t l;
    size_t rank = 0;
    while (rank_reader.next(&f,&d,&l)) if (f == 1) ++rank;
    if (!rank_reader.ok) return invalid("Malformed ONNX input shape");
    if (rank != expected.size()) { *why = "requires rank-4 input"; return AjiFixedShape::Unsupported; }
    Reader r{shape.data,shape.data+shape.len};
    std::string fixed; size_t axis = 0; bool changed = false;
    std::map<std::string,int64_t> symbols;
    while (r.p < r.end) {
        const uint8_t *start = r.p;
        if (!r.next(&f,&d,&l)) return invalid("Malformed ONNX input shape");
        if (f != 1) { fixed.append((const char *)start,(size_t)(r.p-start)); continue; }
        if (!d || axis >= expected.size()) { *why = "requires rank-4 input"; return AjiFixedShape::Unsupported; }
        if (expected[axis] <= 0) return invalid("Expected input dimension must be positive");
        Reader dim{d,d+l}; uint32_t k; const uint8_t *v; size_t z;
        bool value_seen = false, symbol_seen = false; uint64_t value = 0; std::string symbol, rest;
        while (dim.p < dim.end) {
            const uint8_t *part = dim.p;
            if (!dim.next(&k,&v,&z)) return invalid("Malformed ONNX input dimension");
            if (k == 1) {
                if (dim.wire != 0 || value_seen || symbol_seen) return invalid("Ambiguous ONNX input dimension");
                value_seen = true; value = dim.scalar;
            } else if (k == 2) {
                if (!v || value_seen || symbol_seen) return invalid("Ambiguous ONNX input symbol");
                symbol_seen = true; symbol.assign((const char *)v,z);
            } else rest.append((const char *)part,(size_t)(dim.p-part));
        }
        const bool positive = value_seen && value > 0 && value <= INT64_MAX;
        if (positive && value != (uint64_t)expected[axis]) return invalid("Fixed ONNX input dimension conflicts with executor geometry");
        if (!symbol.empty()) {
            const auto item = symbols.emplace(symbol,expected[axis]);
            if (!item.second && item.first->second != expected[axis]) return invalid("ONNX input symbol requires conflicting known dimensions");
        }
        changed = changed || !positive;
        std::string dimension(1,(char)0x08); put_varint(dimension,(uint64_t)expected[axis]); dimension += rest;
        put_varint(fixed,10); put_varint(fixed,dimension.size()); fixed += dimension; ++axis;
    }
    if (axis != expected.size()) { *why = "requires rank-4 input"; return AjiFixedShape::Unsupported; }
    if (!changed) { *why = "input already fixed"; return AjiFixedShape::Unchanged; }
    const auto new_tensor = replace(tensor.data,tensor.len,shape,2,fixed);
    const auto new_type = replace(type.data,type.len,tensor,1,new_tensor);
    const auto new_input = replace(input.data,input.len,type,2,new_type);
    const auto new_graph = replace(graph.data,graph.len,input,11,new_input);
    const auto result = replace(base,model.size(),graph,7,new_graph);
    out->assign(result.begin(),result.end()); *why = "rank-4 input fixed by axis";
    return AjiFixedShape::Specialized;
}

bool aji_onnx_external_locations(const std::vector<char> &model, std::vector<std::string> *locations,
                                  std::string *why)
{
    // ONNX 1.19.1 onnx.proto: only descend into declared message fields.
    // Raw tensor bytes and strings must never be interpreted as protobuf.
    enum class Kind { Model, Graph, Node, Attribute, Tensor, Sparse, Function, Training };
    std::set<std::string> found;
    auto walk = [&](auto &&self, const uint8_t *p, size_t n, Kind kind, unsigned depth) -> bool {
        if (depth > 64) { *why = "ONNX metadata nesting exceeds 64"; return false; }
        Reader r{p, p+n}; uint32_t field; const uint8_t *data; size_t len;
        bool external = false, metadata = false, graph = false;
        std::string location;
        while (r.next(&field, &data, &len)) {
            if (kind == Kind::Tensor && field == 14) external = r.scalar == 1;
            if (!data) continue;
            if (kind == Kind::Tensor && field == 13) {
                metadata = true;
                Reader entry{data, data+len}; uint32_t f; const uint8_t *d; size_t l;
                std::string key, value;
                while (entry.next(&f, &d, &l)) if (d) {
                    if (f == 1) key.assign((const char *)d,l);
                    if (f == 2) value.assign((const char *)d,l);
                }
                if (!entry.ok) { *why = "Malformed ONNX external_data"; return false; }
                if (key == "location") {
                    if (!location.empty() && location != value) { *why = "Conflicting ONNX weight locations"; return false; }
                    location = value;
                }
                continue;
            }
            Kind child = kind; bool descend = true;
            switch (kind) {
            case Kind::Model:
                if (field == 7) { child = Kind::Graph; graph = true; }
                else if (field == 20) child = Kind::Training;
                else if (field == 25) child = Kind::Function;
                else descend = false;
                break;
            case Kind::Graph:
                if (field == 1) child = Kind::Node;
                else if (field == 5) child = Kind::Tensor;
                else if (field == 15) child = Kind::Sparse;
                else descend = false;
                break;
            case Kind::Node: if (field == 5) child = Kind::Attribute; else descend = false; break;
            case Kind::Attribute:
                if (field == 5 || field == 10) child = Kind::Tensor;
                else if (field == 6 || field == 11) child = Kind::Graph;
                else if (field == 22 || field == 23) child = Kind::Sparse;
                else descend = false;
                break;
            case Kind::Sparse: if (field == 1 || field == 2) child = Kind::Tensor; else descend = false; break;
            case Kind::Function:
                if (field == 7) child = Kind::Node;
                else if (field == 11) child = Kind::Attribute;
                else descend = false;
                break;
            case Kind::Training: if (field == 1 || field == 2) child = Kind::Graph; else descend = false; break;
            case Kind::Tensor: descend = false; break;
            }
            if (descend && !self(self,data,len,child,depth+1)) return false;
        }
        if (!r.ok) { *why = "Malformed ONNX weight metadata"; return false; }
        if (kind == Kind::Model && !graph) { *why = "Missing ONNX graph"; return false; }
        if (kind == Kind::Tensor && (external || metadata)) {
            if (location.empty() || location.find('\0') != std::string::npos) { *why = "Missing/invalid ONNX weight location"; return false; }
            found.insert(location);
        }
        return true;
    };
    locations->clear();
    if (model.empty() || !walk(walk,(const uint8_t *)model.data(),model.size(),Kind::Model,0)) return false;
    locations->assign(found.begin(),found.end()); return true;
}

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

bool aji_onnx_motion_outputs(const std::vector<char> &model, std::vector<char> *out,
                             std::string *why)
{
    std::vector<char> expanded;
    if (!aji_onnx_add_flow_outputs(model, &expanded, why)) return false;
    const auto *base = reinterpret_cast<const uint8_t *>(expanded.data());
    Reader top{base, base + expanded.size()};
    const uint8_t *graph = nullptr, *field_start = nullptr, *after = nullptr;
    size_t length = 0;
    while (top.p < top.end && top.ok) {
        const auto *start = top.p; uint32_t field; const uint8_t *data; size_t n;
        if (!top.next(&field, &data, &n)) break;
        if (field == 7 && data) { graph = data; length = n; field_start = start; after = top.p; }
    }
    if (!top.ok || !graph) { *why = "unreadable motion graph"; return false; }
    // The two entries just appended are the desired outputs. Existing output
    // entries (including duplicate flow outputs in an expanded model) go away.
    Reader count{graph, graph + length}; size_t outputs = 0;
    while (count.p < count.end && count.ok) {
        uint32_t field; const uint8_t *data; size_t n;
        if (!count.next(&field, &data, &n)) break;
        if (field == 12) ++outputs;
    }
    if (!count.ok || outputs < 3) { *why = "missing motion graph outputs"; return false; }
    Reader read{graph, graph + length}; std::vector<char> body; size_t index = 0;
    while (read.p < read.end && read.ok) {
        const auto *start = read.p; uint32_t field; const uint8_t *data; size_t n;
        if (!read.next(&field, &data, &n)) break;
        if (field != 12 || ++index > outputs - 2)
            body.insert(body.end(), reinterpret_cast<const char *>(start), reinterpret_cast<const char *>(read.p));
    }
    if (!read.ok) { *why = "truncated motion graph"; return false; }
    std::string head(1, char(0x3a)); put_varint(head, body.size());
    out->clear(); out->reserve(expanded.size());
    out->insert(out->end(), static_cast<const char *>(expanded.data()), reinterpret_cast<const char *>(field_start));
    out->insert(out->end(), head.begin(), head.end()); out->insert(out->end(), body.begin(), body.end());
    out->insert(out->end(), reinterpret_cast<const char *>(after), static_cast<const char *>(expanded.data()) + expanded.size());
    return true;
}
