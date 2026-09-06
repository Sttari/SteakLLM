{{- define "worker.labels" -}}
app.kubernetes.io/name: {{ .Values.name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: steakllm
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
steakllm.io/service: {{ .Values.name }}
steakllm.io/role: worker
{{- end }}

{{- define "worker.selectorLabels" -}}
app.kubernetes.io/name: {{ .Values.name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
