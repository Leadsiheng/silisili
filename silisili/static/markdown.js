/* Small, deliberately HTML-free Markdown renderer for the platform manual. */
(function(root) {
  const escape = text => String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function inline(text) {
    const pattern = /`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*]+)\*\*/g;
    let html='',last=0,match;
    while((match=pattern.exec(text))) {
      html+=escape(text.slice(last,match.index));
      if(match[1])html+='<code>'+escape(match[1])+'</code>';
      else if(match[2])html+='<a href="'+escape(match[3])+'" target="_blank" rel="noopener noreferrer">'+escape(match[2])+'</a>';
      else html+='<strong>'+escape(match[4])+'</strong>';
      last=pattern.lastIndex;
    }
    return html+escape(text.slice(last));
  }
  function render(text) {
    const lines=String(text).replace(/\r\n/g,'\n').split('\n'),out=[];
    let paragraph=[],list=[],listType='',code=null;
    const flushParagraph=()=>{if(paragraph.length){out.push('<p>'+paragraph.map(inline).join('<br>')+'</p>');paragraph=[];}};
    const flushList=()=>{if(list.length){out.push('<'+listType+'>'+list.map(t=>'<li>'+inline(t)+'</li>').join('')+'</'+listType+'>');list=[];}};
    for(const line of lines) {
      if(/^```/.test(line)){flushParagraph();flushList();if(code!==null){out.push('<pre><code>'+escape(code.join('\n'))+'</code></pre>');code=null;}else code=[];continue;}
      if(code!==null){code.push(line);continue;}
      const heading=line.match(/^(#{1,6})\s+(.+)$/),item=line.match(/^\s*(?:([-*])|\d+\.)\s+(.+)$/);
      if(!line.trim()){flushParagraph();flushList();continue;}
      if(heading){flushParagraph();flushList();out.push('<h'+heading[1].length+'>'+inline(heading[2])+'</h'+heading[1].length+'>');continue;}
      if(item){flushParagraph();const type=item[1]?'ul':'ol';if(type!==listType)flushList();listType=type;list.push(item[2]);continue;}
      flushList();paragraph.push(line);
    }
    flushParagraph();flushList();if(code!==null)out.push('<pre><code>'+escape(code.join('\n'))+'</code></pre>');
    return out.join('\n');
  }
  root.renderMarkdown=render;
  if(typeof module!=='undefined')module.exports=render;
})(typeof window!=='undefined'?window:globalThis);
