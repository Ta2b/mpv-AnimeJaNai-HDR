using AnimeJaNai.Platform;
using System.Text;
using System.Text.Json;
string root=Path.GetFullPath(args[0]);if(Directory.Exists(root))throw new Exception("Fixture must be new");Directory.CreateDirectory(root);
var checks=new List<string>();void Check(string name,bool ok){if(!ok)throw new Exception(name);checks.Add(name);}
byte[] Join(params byte[][] arrays)=>arrays.SelectMany(a=>a).ToArray();
byte[] V(ulong n){var a=new List<byte>();while(n>=128){a.Add((byte)(n|128));n>>=7;}a.Add((byte)n);return a.ToArray();}
byte[] Field(int number,byte[] body)=>Join(V((ulong)(number<<3|2)),V((ulong)body.Length),body);
byte[] Text(int number,string value)=>Field(number,Encoding.UTF8.GetBytes(value));
byte[] Input(string name,params long[] dims){
 var shape=Join(dims.Select(d=>Field(1,d==-1?Text(2,"symbol"):Join(V(8),V((ulong)d)))).ToArray());
 return Field(11,Join(Text(1,name),Field(2,Field(1,Join(new byte[]{8,1},Field(2,shape))))));
}
byte[] Model(byte[] graph)=>Field(7,graph);
bool Equal(List<long>? a,List<long>? b)=>a==null?b==null:b!=null&&a.SequenceEqual(b);
void Both(string name,byte[] data,List<long>? expected){
 var reference=OnnxModelShape.InputDims(data);using var stream=new MemoryStream(data,false);var candidate=OnnxModelShape.InputDims(stream);
 Check(name,Equal(reference,candidate)&&Equal(candidate,expected));
}
Both("4D temporal channels",Model(Input("input",1,9,64,64)),[1,9,64,64]);
Both("5D temporal frames",Model(Input("input",1,4,3,64,64)),[1,4,3,64,64]);
Both("symbolic dimensions",Model(Input("input",1,3,-1,-1)),[1,3,-1,-1]);
Both("input also initializer excluded regardless of order",Model(Join(Input("weight",1,99,64,64),Input("real",1,3,64,64),Field(5,Text(8,"weight")))),[1,3,64,64]);
Both("no graph",new byte[]{8,9},null);
Both("no shaped input",Model(Field(11,Text(1,"name-only"))),null);
// Real sparse weight payload; the initializer's name comes AFTER raw_data.
const int weightBytes=128*1024*1024;string large=Path.Combine(root,"large.onnx");
byte[] graphPrefix=Join(Input("weight",1,99,64,64),Input("input",1,3,64,64));
byte[] weightPrefix=Join(V(9*8+2),V(weightBytes)),weightSuffix=Text(8,"weight");
long tensorLength=weightPrefix.Length+(long)weightBytes+weightSuffix.Length;
byte[] tensorPrefix=Join(V(5*8+2),V((ulong)tensorLength));long graphLength=graphPrefix.Length+tensorPrefix.Length+tensorLength;
using(var f=File.Create(large)){
 f.Write(Join(V(7*8+2),V((ulong)graphLength),graphPrefix,tensorPrefix,weightPrefix));f.Seek(weightBytes,SeekOrigin.Current);f.Write(weightSuffix);
}
long started=GC.GetAllocatedBytesForCurrentThread();var oldDims=OnnxModelShape.InputDims(File.ReadAllBytes(large));long oldAllocated=GC.GetAllocatedBytesForCurrentThread()-started;
started=GC.GetAllocatedBytesForCurrentThread();long read,skip;List<long>? newDims;
using(var counting=new CountingStream(File.OpenRead(large))){newDims=OnnxModelShape.InputDims(counting);read=counting.BytesRead;skip=counting.LargestSkip;}
long newAllocated=GC.GetAllocatedBytesForCurrentThread()-started;
Check("sparse payload skipped, initializer name after weights honored",Equal(oldDims,newDims)&&newDims!.SequenceEqual(new long[]{1,3,64,64})&&read<4096&&skip>=weightBytes);
Check("allocation no longer scales with 128MiB weights",oldAllocated>=weightBytes&&newAllocated<1024*1024);
var invalid=new Dictionary<string,byte[]>{
 ["truncated varint"]=[0x3a,0x80],
 ["varint overflow"]=Enumerable.Repeat((byte)0xff,10).ToArray(),
 ["length beyond segment"]=[0x3a,0xff,0x7f],
 ["unsupported wire group"]=[0x0b],
 ["truncated nested fixed64"]=[0x3a,1,0x09],
};
foreach(var (name,data) in invalid){
 bool refused=false;try{using var f=new MemoryStream(data,false);OnnxModelShape.InputDims(f);}catch(Exception e)when(e is InvalidDataException or EndOfStreamException){refused=true;}
 Check(name+" terminates with controlled refusal",refused);
}
string temporal=Path.Combine(root,"temporal.onnx");File.WriteAllBytes(temporal,Model(Input("input",1,9,64,64)));
Check("TemporalFrames wired to stream",OnnxModelShape.TemporalFrames(temporal)==3);
var stamp=File.GetLastWriteTimeUtc(temporal);File.WriteAllBytes(temporal,Model(Input("input",1,15,64,64)));File.SetLastWriteTimeUtc(temporal,stamp.AddSeconds(2));
Check("same-length cache invalidation retained",OnnxModelShape.TemporalFrames(temporal)==5);
string bad=Path.Combine(root,"broken.onnx");File.WriteAllBytes(bad,invalid["truncated varint"]);Check("unreadable model keeps fallback1",OnnxModelShape.TemporalFrames(bad)==1);
var real=new List<object>();foreach(string path in args.Skip(1)){
 var a=OnnxModelShape.InputDims(File.ReadAllBytes(path));using var file=File.OpenRead(path);var b=OnnxModelShape.InputDims(file);Check("real model "+Path.GetFileName(path),Equal(a,b));real.Add(new {model=Path.GetFileName(path),dimensions=b});
}
var receipt=new {passed=true,checks,weightBytes,referenceAllocatedBytes=oldAllocated,streamAllocatedBytes=newAllocated,logicalStreamBytesRead=read,largestSeekSkipped=skip,realModels=real,scope="CPU ONNX metadata only; sparse file/reference byte[] vs streaming, logical reader IO not OS page IO, no video/FPS change claimed"};
string json=JsonSerializer.Serialize(receipt,new JsonSerializerOptions{WriteIndented=true});File.WriteAllText(Path.Combine(root,"receipt.json"),json+"\n");Console.WriteLine(json);
sealed class CountingStream(Stream inner):Stream {
 public long BytesRead{get;private set;}public long LargestSkip{get;private set;}
 public override bool CanRead=>true;public override bool CanSeek=>true;public override bool CanWrite=>false;public override long Length=>inner.Length;
 public override long Position{get=>inner.Position;set{LargestSkip=Math.Max(LargestSkip,Math.Abs(value-inner.Position));inner.Position=value;}}
 public override int ReadByte(){int b=inner.ReadByte();if(b>=0)BytesRead++;return b;}
 public override int Read(byte[] b,int offset,int count){int n=inner.Read(b,offset,count);BytesRead+=n;return n;}
 public override int Read(Span<byte> b){int n=inner.Read(b);BytesRead+=n;return n;}
 public override long Seek(long offset,SeekOrigin origin){long before=inner.Position;long after=inner.Seek(offset,origin);LargestSkip=Math.Max(LargestSkip,Math.Abs(after-before));return after;}
 public override void Flush(){}public override void SetLength(long n)=>throw new NotSupportedException();public override void Write(byte[] b,int o,int n)=>throw new NotSupportedException();
 protected override void Dispose(bool disposing){if(disposing)inner.Dispose();base.Dispose(disposing);}
}
